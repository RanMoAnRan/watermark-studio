from __future__ import annotations

import io
from dataclasses import dataclass
import math
from typing import Literal

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream, DictionaryObject, NameObject


@dataclass(frozen=True)
class CleanResult:
    pdf_bytes: bytes
    removed_watermark_artifacts: int
    removed_watermark_annots: int
    removed_low_opacity_blocks: int
    removed_suspected_image_xobjects: int


def _name(value) -> str | None:
    if value is None:
        return None
    try:
        decoded = value.decode("utf-8")
        return decoded
    except Exception:
        pass
    return str(value)


def _resolve(value):
    try:
        return value.get_object()
    except Exception:
        return value


def _dict_get(dct, key, default=None):
    if dct is None:
        return default
    try:
        return dct.get(key, default)
    except Exception:
        return default


def _as_text(value) -> str:
    if value is None:
        return ""
    value = _resolve(value)
    try:
        return str(value)
    except Exception:
        return ""


def _remove_watermark_annotations(page) -> int:
    annots = page.get("/Annots")
    if not annots:
        return 0

    kept = []
    removed = 0
    for annot_ref in annots:
        annot = annot_ref.get_object()
        subtype = _name(annot.get("/Subtype"))
        if subtype in {"/Watermark", "/Stamp"}:
            removed += 1
            continue
        kept.append(annot_ref)

    if removed:
        if kept:
            page[NameObject("/Annots")] = kept
        else:
            page.pop("/Annots", None)
    return removed


def _is_watermark_artifact(operands) -> bool:
    if not operands:
        return False

    tag = _name(operands[0])
    if tag != "/Artifact":
        return False

    if len(operands) < 2:
        return False

    props = operands[1]
    props = _resolve(props)

    if not hasattr(props, "get"):
        return False

    subtype = _name(props.get("/Subtype"))
    return subtype == "/Watermark"


def _is_ocg_watermark(operands, page) -> bool:
    if not operands or len(operands) < 2:
        return False

    tag = _name(operands[0])
    if tag != "/OC":
        return False

    props = _resolve(operands[1])
    resources = _resolve(page.get("/Resources"))
    properties = _resolve(_dict_get(resources, "/Properties"))

    ocg = None
    if hasattr(props, "get"):
        ocg = props
    elif properties and hasattr(properties, "get"):
        ocg = _resolve(properties.get(props))

    if not ocg or not hasattr(ocg, "get"):
        return False

    name = _as_text(ocg.get("/Name")).lower()
    if "watermark" in name or "水印" in name:
        return True

    intent = _resolve(ocg.get("/Intent"))
    intent_text = _as_text(intent).lower()
    if "watermark" in intent_text or "/watermark" in intent_text:
        return True

    return False


def _strip_marked_watermarks(page, reader: PdfReader) -> int:
    contents = page.get_contents()
    if contents is None:
        return 0

    content = ContentStream(contents, reader)
    original_ops = list(content.operations)
    new_ops = []

    skip_depth = 0
    skip_stack: list[bool] = []
    removed_ops = 0

    for operands, operator in original_ops:
        op = _name(operator)

        if op in {"BMC", "BDC"}:
            starts_skip = False
            if op == "BDC":
                starts_skip = _is_watermark_artifact(operands) or _is_ocg_watermark(operands, page)
            skip_stack.append(starts_skip)
            if starts_skip:
                skip_depth += 1
            if skip_depth > 0:
                removed_ops += 1
                continue
            new_ops.append((operands, operator))
            continue

        if op == "EMC":
            was_skipping = skip_depth > 0
            started_skip = skip_stack.pop() if skip_stack else False
            if started_skip and skip_depth > 0:
                skip_depth -= 1
            if was_skipping:
                removed_ops += 1
                continue
            new_ops.append((operands, operator))
            continue

        if skip_depth > 0:
            removed_ops += 1
            continue

        new_ops.append((operands, operator))

    if removed_ops:
        content.operations = new_ops
        page[NameObject("/Contents")] = content
    return removed_ops


def _extgstate_alpha(page, gs_name) -> float | None:
    resources = _resolve(page.get("/Resources"))
    extgs = _resolve(_dict_get(resources, "/ExtGState"))
    if not extgs or not hasattr(extgs, "get"):
        return None
    state = _resolve(extgs.get(gs_name))
    if not state or not hasattr(state, "get"):
        return None
    ca = _dict_get(state, "/ca")
    CA = _dict_get(state, "/CA")
    candidates = []
    for v in (ca, CA):
        if v is None:
            continue
        try:
            candidates.append(float(v))
        except Exception:
            continue
    if not candidates:
        return None
    return min(candidates)


def _strip_low_opacity_q_blocks(page, reader: PdfReader, *, alpha_threshold: float = 0.35) -> int:
    contents = page.get_contents()
    if contents is None:
        return 0

    content = ContentStream(contents, reader)
    original_ops = list(content.operations)

    @dataclass
    class _Block:
        ops: list
        current_alpha: float | None
        min_alpha: float | None
        has_text: bool
        has_xobject: bool
        has_rotation: bool
        max_font_size: float

    def _should_drop(block: _Block) -> bool:
        if block.min_alpha is not None and block.min_alpha <= alpha_threshold and (block.has_text or block.has_xobject):
            return True
        if block.has_text and block.has_rotation and block.max_font_size >= 40:
            return True
        return False

    root = _Block(
        ops=[],
        current_alpha=None,
        min_alpha=None,
        has_text=False,
        has_xobject=False,
        has_rotation=False,
        max_font_size=0.0,
    )
    stack: list[_Block] = [root]
    removed_blocks = 0

    for operands, operator in original_ops:
        op = _name(operator)
        cur = stack[-1]

        if op == "q":
            child = _Block(
                ops=[(operands, operator)],
                current_alpha=cur.current_alpha,
                min_alpha=cur.current_alpha,
                has_text=False,
                has_xobject=False,
                has_rotation=False,
                max_font_size=0.0,
            )
            stack.append(child)
            continue

        if op == "Q":
            cur.ops.append((operands, operator))
            if len(stack) > 1:
                finished = stack.pop()
                if _should_drop(finished):
                    removed_blocks += 1
                else:
                    stack[-1].ops.extend(finished.ops)
            else:
                cur.ops.append((operands, operator))
            continue

        if op == "gs" and operands:
            gs_name = operands[0]
            alpha = _extgstate_alpha(page, gs_name)
            if alpha is not None:
                cur.current_alpha = alpha
                cur.min_alpha = alpha if cur.min_alpha is None else min(cur.min_alpha, alpha)

        if op in {"Tj", "TJ", "'", '"'}:
            cur.has_text = True

        if op == "Do":
            cur.has_xobject = True

        if op == "cm" and operands and len(operands) >= 6:
            try:
                b = float(operands[1])
                c = float(operands[2])
                if abs(b) > 1e-6 or abs(c) > 1e-6:
                    cur.has_rotation = True
            except Exception:
                pass

        if op == "Tf" and operands and len(operands) >= 2:
            try:
                font_size = float(operands[1])
                cur.max_font_size = max(cur.max_font_size, font_size)
            except Exception:
                pass

        cur.ops.append((operands, operator))

    while len(stack) > 1:
        finished = stack.pop()
        stack[-1].ops.extend(finished.ops)

    if removed_blocks:
        content.operations = root.ops
        page[NameObject("/Contents")] = content
    return removed_blocks


def _wrap_page_contents_as_artifact_watermark(page, reader: PdfReader) -> None:
    contents = page.get_contents()
    if contents is None:
        return

    content = ContentStream(contents, reader)
    props = DictionaryObject()
    props[NameObject("/Subtype")] = NameObject("/Watermark")
    content.operations = [([NameObject("/Artifact"), props], b"BDC"), *content.operations, ([], b"EMC")]
    page[NameObject("/Contents")] = content


def _strip_suspected_image_xobjects(
    page,
    reader: PdfReader,
    *,
    alpha_threshold: float = 0.6,
    min_scale_ratio: float = 0.22,
) -> int:
    contents = page.get_contents()
    if contents is None:
        return 0

    try:
        page_w = float(page.mediabox.width)
        page_h = float(page.mediabox.height)
    except Exception:
        page_w = 0.0
        page_h = 0.0

    content = ContentStream(contents, reader)
    original_ops = list(content.operations)

    @dataclass
    class _State:
        alpha: float | None
        min_alpha: float | None
        last_cm: tuple[bool, float, float] | None  # (rotated, scale_x, scale_y)

    def _matrix_info(operands) -> tuple[bool, float, float] | None:
        if not operands or len(operands) < 6:
            return None
        try:
            a, b, c, d = (float(operands[i]) for i in range(4))
        except Exception:
            return None
        rotated = (abs(b) > 1e-6) or (abs(c) > 1e-6)
        sx = math.sqrt(a * a + b * b)
        sy = math.sqrt(c * c + d * d)
        return rotated, sx, sy

    def _update_alpha(state: _State, alpha: float) -> None:
        state.alpha = alpha
        state.min_alpha = alpha if state.min_alpha is None else min(state.min_alpha, alpha)

    def _scale_ratio(state: _State) -> tuple[float | None, float | None, bool]:
        if not state.last_cm or page_w <= 0 or page_h <= 0:
            return None, None, False
        rotated, sx, sy = state.last_cm
        return sx / page_w, sy / page_h, rotated

    # pass-1: collect repeated XObject patterns
    from collections import defaultdict

    counts_total: dict[str, int] = defaultdict(int)
    counts_in_q: dict[str, int] = defaultdict(int)
    scale_samples: dict[str, list[tuple[float, float, bool]]] = defaultdict(list)
    state_stack: list[_State] = [_State(alpha=None, min_alpha=None, last_cm=None)]
    for operands, operator in original_ops:
        op = _name(operator)
        cur = state_stack[-1]
        if op == "q":
            state_stack.append(_State(alpha=cur.alpha, min_alpha=cur.min_alpha, last_cm=cur.last_cm))
            continue
        if op == "Q":
            if len(state_stack) > 1:
                state_stack.pop()
            continue
        if op == "gs" and operands:
            alpha = _extgstate_alpha(page, operands[0])
            if alpha is not None:
                _update_alpha(cur, alpha)
            continue
        if op == "cm":
            info = _matrix_info(operands)
            if info is not None:
                cur.last_cm = info
            continue
        if op == "Do" and operands:
            name = _name(operands[0]) or ""
            counts_total[name] += 1
            if len(state_stack) > 1:
                counts_in_q[name] += 1
            rx, ry, rotated = _scale_ratio(cur)
            if rx is not None and ry is not None:
                scale_samples[name].append((rx, ry, rotated))

    suspicious_names: set[str] = set()
    for name, in_q_count in counts_in_q.items():
        total = counts_total.get(name, 0)
        if in_q_count < 6 or total <= 0:
            continue
        if in_q_count / total < 0.85:
            continue
        samples = scale_samples.get(name) or []
        if not samples:
            continue
        rx_med = sorted(s[0] for s in samples)[len(samples) // 2]
        ry_med = sorted(s[1] for s in samples)[len(samples) // 2]
        rotated_any = any(s[2] for s in samples)
        if rotated_any or (rx_med >= 0.05 and ry_med >= 0.05 and rx_med <= 0.75 and ry_med <= 0.75):
            suspicious_names.add(name)

    # pass-2: remove suspicious XObject draws
    new_ops = []
    stack: list[_State] = [_State(alpha=None, min_alpha=None, last_cm=None)]
    removed = 0

    for operands, operator in original_ops:
        op = _name(operator)
        cur = stack[-1]

        if op == "q":
            stack.append(_State(alpha=cur.alpha, min_alpha=cur.min_alpha, last_cm=cur.last_cm))
            new_ops.append((operands, operator))
            continue

        if op == "Q":
            if len(stack) > 1:
                stack.pop()
            new_ops.append((operands, operator))
            continue

        if op == "gs" and operands:
            gs_name = operands[0]
            alpha = _extgstate_alpha(page, gs_name)
            if alpha is not None:
                _update_alpha(cur, alpha)
            new_ops.append((operands, operator))
            continue

        if op == "cm":
            info = _matrix_info(operands)
            if info is not None:
                cur.last_cm = info
            new_ops.append((operands, operator))
            continue

        if op == "Do":
            inside_q = len(stack) > 1
            suspicious = False
            do_name = _name(operands[0]) if operands else None
            if inside_q and do_name and do_name in suspicious_names:
                removed += 1
                continue

            if cur.min_alpha is not None and cur.min_alpha <= alpha_threshold:
                suspicious = True

            if not suspicious and cur.last_cm and page_w > 0 and page_h > 0:
                rotated, sx, sy = cur.last_cm
                if rotated:
                    rx = sx / page_w
                    ry = sy / page_h
                    if rx >= min_scale_ratio and ry >= min_scale_ratio:
                        suspicious = True

            if inside_q and suspicious:
                removed += 1
                continue

        new_ops.append((operands, operator))

    if removed:
        content.operations = new_ops
        page[NameObject("/Contents")] = content
    return removed


def clean_pdf_watermarks(pdf_bytes: bytes, *, enhanced: bool = True, remove_image_watermarks: bool = False) -> CleanResult:
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("Not a valid PDF file.")

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()

    removed_annots = 0
    removed_artifacts = 0
    removed_low_opacity_blocks = 0
    removed_suspected_image_xobjects = 0

    for page in reader.pages:
        removed_annots += _remove_watermark_annotations(page)
        removed_artifacts += _strip_marked_watermarks(page, reader)
        if enhanced:
            removed_low_opacity_blocks += _strip_low_opacity_q_blocks(page, reader)
        if remove_image_watermarks:
            removed_suspected_image_xobjects += _strip_suspected_image_xobjects(page, reader)
        writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    return CleanResult(
        pdf_bytes=out.getvalue(),
        removed_watermark_artifacts=removed_artifacts,
        removed_watermark_annots=removed_annots,
        removed_low_opacity_blocks=removed_low_opacity_blocks,
        removed_suspected_image_xobjects=removed_suspected_image_xobjects,
    )


def compare_pdf_text(before_pdf: bytes, after_pdf: bytes, *, max_pages: int = 12, max_chars: int = 80_000) -> dict:
    def _extract_text(pdf_bytes: bytes) -> str:
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
        except Exception:
            return ""
        parts: list[str] = []
        for i, page in enumerate(reader.pages):
            if i >= max_pages:
                break
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            if t:
                parts.append(t)
            if sum(len(p) for p in parts) >= max_chars:
                break
        text = "\n".join(parts)
        return text[:max_chars]

    before_text = _extract_text(before_pdf)
    after_text = _extract_text(after_pdf)

    try:
        import difflib

        ratio = difflib.SequenceMatcher(None, before_text, after_text).ratio()
    except Exception:
        ratio = None

    return {
        "pages_sampled": max_pages,
        "before_len": len(before_text),
        "after_len": len(after_text),
        "similarity": ratio,
    }


PdfPosition = Literal[
    "top_left",
    "top_right",
    "center",
    "bottom_left",
    "bottom_right",
]


@dataclass(frozen=True)
class PdfTextWatermarkOptions:
    position: PdfPosition = "center"
    font_size: int = 48
    rotation: int = 30
    color_hex: str = "#111827"
    opacity: float = 0.18
    style: Literal["single", "tile"] = "tile"
    margin: int = 36

    @staticmethod
    def from_form(form) -> "PdfTextWatermarkOptions":
        def _int(name: str, default: int, min_v: int, max_v: int) -> int:
            try:
                v = int(form.get(name, default))
            except Exception:
                return default
            return max(min_v, min(max_v, v))

        def _float(name: str, default: float, min_v: float, max_v: float) -> float:
            try:
                v = float(form.get(name, default))
            except Exception:
                return default
            return max(min_v, min(max_v, v))

        position = form.get("position") or "center"
        if position not in {"top_left", "top_right", "center", "bottom_left", "bottom_right"}:
            position = "center"

        style = form.get("style") or "tile"
        if style not in {"single", "tile"}:
            style = "tile"

        color_hex = (form.get("color") or "#111827").strip()
        if not color_hex.startswith("#") or len(color_hex) not in {4, 7}:
            color_hex = "#111827"

        return PdfTextWatermarkOptions(
            position=position,  # type: ignore[arg-type]
            font_size=_int("font_size", 48, 8, 200),
            rotation=_int("rotation", 30, -180, 180),
            color_hex=color_hex,
            opacity=_float("opacity", 0.18, 0.02, 1.0),
            style=style,  # type: ignore[arg-type]
            margin=_int("margin", 36, 0, 200),
        )


@dataclass(frozen=True)
class PdfImageWatermarkOptions:
    position: PdfPosition = "center"
    rotation: int = 0
    opacity: float = 0.35
    style: Literal["single", "tile"] = "single"
    margin: int = 36
    width_percent: int = 25

    @staticmethod
    def from_form(form) -> "PdfImageWatermarkOptions":
        def _int(name: str, default: int, min_v: int, max_v: int) -> int:
            try:
                v = int(form.get(name, default))
            except Exception:
                return default
            return max(min_v, min(max_v, v))

        def _float(name: str, default: float, min_v: float, max_v: float) -> float:
            try:
                v = float(form.get(name, default))
            except Exception:
                return default
            return max(min_v, min(max_v, v))

        position = form.get("img_position") or form.get("position") or "center"
        if position not in {"top_left", "top_right", "center", "bottom_left", "bottom_right"}:
            position = "center"

        style = form.get("img_style") or form.get("style") or "single"
        if style not in {"single", "tile"}:
            style = "single"

        return PdfImageWatermarkOptions(
            position=position,  # type: ignore[arg-type]
            rotation=_int("img_rotation", _int("rotation", 0, -180, 180), -180, 180),
            opacity=_float("img_opacity", _float("opacity", 0.35, 0.02, 1.0), 0.02, 1.0),
            style=style,  # type: ignore[arg-type]
            margin=_int("img_margin", _int("margin", 36, 0, 200), 0, 200),
            width_percent=_int("img_width_percent", 25, 5, 90),
        )


def pdf_add_text_watermark(pdf_bytes: bytes, *, text: str, options: PdfTextWatermarkOptions) -> bytes:
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("Not a valid PDF file.")

    try:
        from reportlab.lib.colors import Color
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfgen import canvas
    except Exception as exc:
        raise RuntimeError("缺少依赖：请安装 reportlab 以支持 PDF 添加水印。") from exc

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()

    def _hex_to_rgb(hex_str: str) -> tuple[float, float, float]:
        s = hex_str.lstrip("#")
        if len(s) == 3:
            r, g, b = (int(ch * 2, 16) for ch in s)
        else:
            r, g, b = (int(s[i : i + 2], 16) for i in (0, 2, 4))
        return r / 255.0, g / 255.0, b / 255.0

    r, g, b = _hex_to_rgb(options.color_hex)
    fill = Color(r, g, b, alpha=options.opacity)

    def _choose_font_name(value: str) -> str:
        if any(ord(ch) > 127 for ch in value):
            try:
                pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
                return "STSong-Light"
            except Exception:
                return "Helvetica"
        return "Helvetica"

    font_name = _choose_font_name(text)

    for page in reader.pages:
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)

        overlay = io.BytesIO()
        c = canvas.Canvas(overlay, pagesize=(width, height))
        c.setFillColor(fill)
        c.setFont(font_name, options.font_size)

        def _draw_one(x: float, y: float) -> None:
            c.saveState()
            c.translate(x, y)
            c.rotate(options.rotation)
            c.drawCentredString(0, 0, text)
            c.restoreState()

        if options.style == "single":
            x, y = width / 2, height / 2
            m = options.margin
            if options.position == "top_left":
                x, y = m, height - m
            elif options.position == "top_right":
                x, y = width - m, height - m
            elif options.position == "bottom_left":
                x, y = m, m
            elif options.position == "bottom_right":
                x, y = width - m, m
            _draw_one(x, y)
        else:
            step_x = max(160, options.font_size * 5)
            step_y = max(120, options.font_size * 3)
            for yy in range(0, int(height) + step_y, step_y):
                for xx in range(0, int(width) + step_x, step_x):
                    _draw_one(xx, yy)

        c.showPage()
        c.save()
        overlay.seek(0)

        overlay_reader = PdfReader(overlay)
        watermark_page = overlay_reader.pages[0]
        _wrap_page_contents_as_artifact_watermark(watermark_page, overlay_reader)
        page.merge_page(watermark_page)
        writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def pdf_add_image_watermark(pdf_bytes: bytes, *, image_bytes: bytes, options: PdfImageWatermarkOptions) -> bytes:
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("Not a valid PDF file.")

    try:
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
    except Exception as exc:
        raise RuntimeError("缺少依赖：请安装 reportlab 以支持 PDF 添加水印。") from exc

    try:
        from PIL import Image
    except Exception as exc:
        raise RuntimeError("缺少依赖：请安装 Pillow 以支持图片水印。") from exc

    try:
        wm = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    except Exception as exc:
        raise ValueError("水印图片不可读取，请换一张 PNG/JPG/WEBP。") from exc

    if options.opacity < 1.0:
        alpha = wm.getchannel("A")
        alpha = alpha.point(lambda p: int(p * max(0.0, min(1.0, options.opacity))))
        wm.putalpha(alpha)

    wm_buf = io.BytesIO()
    wm.save(wm_buf, format="PNG", optimize=True)
    wm_buf.seek(0)

    wm_reader = ImageReader(wm_buf)
    wm_w_px, wm_h_px = wm.size
    if wm_w_px <= 0 or wm_h_px <= 0:
        raise ValueError("水印图片尺寸异常。")

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()

    for page in reader.pages:
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)

        overlay = io.BytesIO()
        c = canvas.Canvas(overlay, pagesize=(width, height))

        target_w = width * (options.width_percent / 100.0)
        target_h = target_w * (wm_h_px / wm_w_px)

        def _draw_one(center_x: float, center_y: float) -> None:
            c.saveState()
            c.translate(center_x, center_y)
            if options.rotation:
                c.rotate(options.rotation)
            c.drawImage(
                wm_reader,
                -target_w / 2,
                -target_h / 2,
                width=target_w,
                height=target_h,
                mask="auto",
                preserveAspectRatio=True,
            )
            c.restoreState()

        if options.style == "single":
            cx, cy = width / 2, height / 2
            m = options.margin
            if options.position == "top_left":
                cx, cy = m + target_w / 2, height - m - target_h / 2
            elif options.position == "top_right":
                cx, cy = width - m - target_w / 2, height - m - target_h / 2
            elif options.position == "bottom_left":
                cx, cy = m + target_w / 2, m + target_h / 2
            elif options.position == "bottom_right":
                cx, cy = width - m - target_w / 2, m + target_h / 2
            _draw_one(cx, cy)
        else:
            step_x = max(80.0, target_w + options.margin)
            step_y = max(80.0, target_h + options.margin)
            y = 0.0
            while y <= height + step_y:
                x = 0.0
                while x <= width + step_x:
                    _draw_one(x, y)
                    x += step_x
                y += step_y

        c.showPage()
        c.save()
        overlay.seek(0)

        overlay_reader = PdfReader(overlay)
        watermark_page = overlay_reader.pages[0]
        _wrap_page_contents_as_artifact_watermark(watermark_page, overlay_reader)
        page.merge_page(watermark_page)
        writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
