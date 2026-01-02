from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageDraw, ImageOps


class InvalidImageComposeOptionsError(ValueError):
    pass


@dataclass(frozen=True)
class ComposeSlot:
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1


@dataclass(frozen=True)
class ComposeLayout:
    key: str
    name: str
    rows: int
    cols: int
    slots: tuple[ComposeSlot, ...]

    @property
    def needed_images(self) -> int:
        return len(self.slots)


LAYOUTS: dict[str, ComposeLayout] = {
    "mt_2_lr": ComposeLayout(
        key="mt_2_lr",
        name="两张（左右）",
        rows=1,
        cols=2,
        slots=(ComposeSlot(0, 0), ComposeSlot(0, 1)),
    ),
    "mt_2_tb": ComposeLayout(
        key="mt_2_tb",
        name="两张（上下）",
        rows=2,
        cols=1,
        slots=(ComposeSlot(0, 0), ComposeSlot(1, 0)),
    ),
    "mt_3_lr": ComposeLayout(
        key="mt_3_lr",
        name="三张（左右）",
        rows=1,
        cols=3,
        slots=(ComposeSlot(0, 0), ComposeSlot(0, 1), ComposeSlot(0, 2)),
    ),
    "mt_3_tb": ComposeLayout(
        key="mt_3_tb",
        name="三张（上下）",
        rows=3,
        cols=1,
        slots=(ComposeSlot(0, 0), ComposeSlot(1, 0), ComposeSlot(2, 0)),
    ),
    "mt_4": ComposeLayout(
        key="mt_4",
        name="四宫格（2×2）",
        rows=2,
        cols=2,
        slots=(ComposeSlot(0, 0), ComposeSlot(0, 1), ComposeSlot(1, 0), ComposeSlot(1, 1)),
    ),
    "mt_6": ComposeLayout(
        key="mt_6",
        name="六宫格（2×3）",
        rows=2,
        cols=3,
        slots=(
            ComposeSlot(0, 0),
            ComposeSlot(0, 1),
            ComposeSlot(0, 2),
            ComposeSlot(1, 0),
            ComposeSlot(1, 1),
            ComposeSlot(1, 2),
        ),
    ),
    "mt_9": ComposeLayout(
        key="mt_9",
        name="九宫格（3×3）",
        rows=3,
        cols=3,
        slots=(
            ComposeSlot(0, 0),
            ComposeSlot(0, 1),
            ComposeSlot(0, 2),
            ComposeSlot(1, 0),
            ComposeSlot(1, 1),
            ComposeSlot(1, 2),
            ComposeSlot(2, 0),
            ComposeSlot(2, 1),
            ComposeSlot(2, 2),
        ),
    ),
    # Meitu-style: one big + two small (square canvas)
    "mt_big_left_2": ComposeLayout(
        key="mt_big_left_2",
        name="三张（左大右二）",
        rows=2,
        cols=2,
        slots=(ComposeSlot(0, 0, row_span=2, col_span=1), ComposeSlot(0, 1), ComposeSlot(1, 1)),
    ),
    "mt_big_top_2": ComposeLayout(
        key="mt_big_top_2",
        name="三张（上大下二）",
        rows=2,
        cols=2,
        slots=(ComposeSlot(0, 0, row_span=1, col_span=2), ComposeSlot(1, 0), ComposeSlot(1, 1)),
    ),
}


def _clamp_int(v: int, min_v: int, max_v: int) -> int:
    return max(min_v, min(max_v, int(v)))


def _parse_int(raw: str, default: int) -> int:
    try:
        return int(str(raw).strip())
    except Exception:
        return int(default)


def _parse_hex_color(raw: str) -> tuple[int, int, int, int]:
    s = (raw or "").strip().lower()
    if not s:
        return 255, 255, 255, 255
    if s in {"transparent", "none"}:
        return 0, 0, 0, 0
    if not s.startswith("#"):
        s = "#" + s
    if re.fullmatch(r"#[0-9a-f]{6}", s):
        r = int(s[1:3], 16)
        g = int(s[3:5], 16)
        b = int(s[5:7], 16)
        return r, g, b, 255
    raise InvalidImageComposeOptionsError("背景色格式不正确，请使用 #RRGGBB。")


@dataclass(frozen=True)
class ImageComposeOptions:
    layout: str
    out_w_px: int
    gap_px: int
    padding_px: int
    radius_px: int
    bg_color: str
    output_format: str  # png|jpg|webp

    @classmethod
    def from_form(cls, form) -> "ImageComposeOptions":
        layout = (form.get("layout") or "mt_2_lr").strip()
        if layout not in LAYOUTS:
            layout = "mt_2_lr"

        out_w_px = _clamp_int(_parse_int(form.get("out_w_px") or "2048", 2048), 512, 8192)
        gap_px = _clamp_int(_parse_int(form.get("gap_px") or "12", 12), 0, 200)
        padding_px = _clamp_int(_parse_int(form.get("padding_px") or "12", 12), 0, 400)
        radius_px = _clamp_int(_parse_int(form.get("radius_px") or "18", 18), 0, 400)
        bg_color = (form.get("bg_color") or "#ffffff").strip()

        output_format = (form.get("output_format") or "png").strip().lower()
        if output_format not in {"png", "jpg", "webp"}:
            output_format = "png"

        return cls(
            layout=layout,
            out_w_px=out_w_px,
            gap_px=gap_px,
            padding_px=padding_px,
            radius_px=radius_px,
            bg_color=bg_color,
            output_format=output_format,
        )


def _rounded_mask(size: tuple[int, int], radius_px: int) -> Image.Image | None:
    w, h = size
    if radius_px <= 0:
        return None
    r = int(min(radius_px, w // 2, h // 2))
    if r <= 0:
        return None
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, w, h), radius=r, fill=255)
    return mask


def _cover_crop(img: Image.Image, *, out_w: int, out_h: int) -> Image.Image:
    if out_w <= 0 or out_h <= 0:
        raise InvalidImageComposeOptionsError("输出尺寸不正确。")
    src_w, src_h = img.size
    if src_w <= 0 or src_h <= 0:
        raise InvalidImageComposeOptionsError("图片尺寸不正确。")

    scale = max(out_w / src_w, out_h / src_h)
    rw = max(1, int(math.ceil(src_w * scale)))
    rh = max(1, int(math.ceil(src_h * scale)))
    resized = img.resize((rw, rh), Image.Resampling.LANCZOS)
    left = max(0, (rw - out_w) // 2)
    top = max(0, (rh - out_h) // 2)
    return resized.crop((left, top, left + out_w, top + out_h))


def _encode_image(img: Image.Image, *, output_format: str, bg_rgba: tuple[int, int, int, int]) -> tuple[bytes, str, str]:
    fmt = output_format.lower()
    if fmt == "jpg":
        pil_format = "JPEG"
        mimetype = "image/jpeg"
        suffix = ".jpg"
        # Flatten alpha.
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        if bg_rgba[3] < 255:
            bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        else:
            bg = Image.new("RGBA", img.size, bg_rgba)
        bg.alpha_composite(img)
        img = bg.convert("RGB")
        save_kwargs = {"quality": 95, "subsampling": 0, "optimize": True, "progressive": True}
    elif fmt == "webp":
        pil_format = "WEBP"
        mimetype = "image/webp"
        suffix = ".webp"
        img = img.convert("RGBA")
        save_kwargs = {"lossless": True, "method": 6, "quality": 100}
    else:
        pil_format = "PNG"
        mimetype = "image/png"
        suffix = ".png"
        img = img.convert("RGBA")
        save_kwargs = {"optimize": True}

    out = io.BytesIO()
    img.save(out, format=pil_format, **save_kwargs)
    return out.getvalue(), mimetype, suffix


def compose_images(image_bytes_list: list[bytes], *, options: ImageComposeOptions) -> tuple[bytes, str, str, dict]:
    layout = LAYOUTS.get(options.layout)
    if not layout:
        raise InvalidImageComposeOptionsError("拼装样式不支持。")

    if len(image_bytes_list) < layout.needed_images:
        raise InvalidImageComposeOptionsError(f"该样式需要 {layout.needed_images} 张图片。")

    bg_rgba = _parse_hex_color(options.bg_color)
    gap = int(options.gap_px)
    pad = int(options.padding_px)

    available_w = options.out_w_px - pad * 2 - gap * (layout.cols - 1)
    if available_w <= 0:
        raise InvalidImageComposeOptionsError("输出宽度过小（请增大导出宽度或减小边距/间距）。")

    cell = max(1, int(available_w // layout.cols))
    out_w = pad * 2 + cell * layout.cols + gap * (layout.cols - 1)
    out_h = pad * 2 + cell * layout.rows + gap * (layout.rows - 1)
    if out_w <= 0 or out_h <= 0:
        raise InvalidImageComposeOptionsError("输出尺寸不正确。")

    canvas = Image.new("RGBA", (out_w, out_h), bg_rgba)

    for idx, slot in enumerate(layout.slots):
        raw = image_bytes_list[idx]
        try:
            src = Image.open(io.BytesIO(raw))
            src.load()
            src = ImageOps.exif_transpose(src)
        except Exception as exc:
            raise InvalidImageComposeOptionsError(f"第 {idx + 1} 张图片无法解析：{exc}") from exc

        src = src.convert("RGBA")
        x = pad + slot.col * cell + slot.col * gap
        y = pad + slot.row * cell + slot.row * gap
        w = slot.col_span * cell + (slot.col_span - 1) * gap
        h = slot.row_span * cell + (slot.row_span - 1) * gap
        if w <= 0 or h <= 0:
            continue

        tile = _cover_crop(src, out_w=w, out_h=h)
        mask = _rounded_mask((w, h), options.radius_px)
        if mask is not None:
            alpha = tile.getchannel("A")
            tile.putalpha(ImageChops.multiply(alpha, mask))
        canvas.alpha_composite(tile, dest=(x, y))

    payload, mimetype, suffix = _encode_image(canvas, output_format=options.output_format, bg_rgba=bg_rgba)
    meta = {
        "layout": layout.key,
        "layout_name": layout.name,
        "out_w": out_w,
        "out_h": out_h,
        "cell": cell,
        "needed_images": layout.needed_images,
    }
    return payload, mimetype, suffix, meta

