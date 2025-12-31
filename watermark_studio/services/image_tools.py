from __future__ import annotations

import io
from dataclasses import dataclass
import json
from typing import Literal


def _require_pillow():
    try:
        from PIL import Image
    except Exception as exc:
        raise RuntimeError("缺少依赖：请安装 Pillow 以支持图片处理。") from exc
    return Image


def _require_cv2():
    try:
        import cv2  # type: ignore
    except Exception as exc:
        raise RuntimeError("缺少依赖：请安装 opencv-python-headless 以支持图片去水印。") from exc
    return cv2


ImagePosition = Literal[
    "top_left",
    "top_right",
    "center",
    "bottom_left",
    "bottom_right",
]

def _find_font_path() -> str | None:
    import os

    override = os.environ.get("WATERMARK_FONT_PATH")
    if override and os.path.exists(override):
        return override

    candidates = [
        # macOS (Chinese-friendly)
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/Library/Fonts/Arial.ttf",
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        # Windows
        "C:\\Windows\\Fonts\\msyh.ttc",
        "C:\\Windows\\Fonts\\simsun.ttc",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _load_font(font_size: int):
    from PIL import ImageFont

    font_size = max(8, int(font_size))
    font_path = _find_font_path()
    if font_path:
        try:
            return ImageFont.truetype(font_path, font_size)
        except Exception:
            pass
    return ImageFont.load_default()


def _luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = (c / 255.0 for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


@dataclass(frozen=True)
class ImageTextWatermarkOptions:
    position: ImagePosition = "bottom_right"
    font_size: int = 36
    rotation: int = 0
    color_hex: str = "#111827"
    opacity: float = 0.35
    style: Literal["single", "tile"] = "single"
    margin: int = 24

    @staticmethod
    def from_form(form) -> "ImageTextWatermarkOptions":
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

        position = form.get("position") or "bottom_right"
        if position not in {"top_left", "top_right", "center", "bottom_left", "bottom_right"}:
            position = "bottom_right"

        style = form.get("style") or "single"
        if style not in {"single", "tile"}:
            style = "single"

        color_hex = (form.get("color") or "#111827").strip()
        if not color_hex.startswith("#") or len(color_hex) not in {4, 7}:
            color_hex = "#111827"

        return ImageTextWatermarkOptions(
            position=position,  # type: ignore[arg-type]
            font_size=_int("font_size", 36, 8, 240),
            rotation=_int("rotation", 0, -180, 180),
            color_hex=color_hex,
            opacity=_float("opacity", 0.35, 0.02, 1.0),
            style=style,  # type: ignore[arg-type]
            margin=_int("margin", 24, 0, 200),
        )


@dataclass(frozen=True)
class ImageRemoveWatermarkOptions:
    regions: list[tuple[float, float, float, float]] | None = None  # normalized (x,y,w,h)
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    auto_strength: int = 40
    inpaint_radius: int = 3
    method: Literal["telea", "ns"] = "telea"
    mask_expand: int = 2

    @property
    def has_region(self) -> bool:
        return self.x is not None and self.y is not None and self.w is not None and self.h is not None

    @property
    def has_regions(self) -> bool:
        return bool(self.regions)

    @staticmethod
    def from_form(form) -> "ImageRemoveWatermarkOptions":
        def _int(name: str, default: int, min_v: int, max_v: int) -> int:
            try:
                v = int(form.get(name, default))
            except Exception:
                return default
            return max(min_v, min(max_v, v))

        def _float_opt(name: str) -> float | None:
            raw = form.get(name)
            if raw is None or raw == "":
                return None
            try:
                v = float(raw)
            except Exception:
                return None
            return max(0.0, min(1.0, v))

        regions = None
        raw_regions = form.get("regions")
        if raw_regions:
            try:
                parsed = json.loads(raw_regions)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                out: list[tuple[float, float, float, float]] = []
                for item in parsed[:12]:
                    if not isinstance(item, dict):
                        continue
                    try:
                        x = float(item.get("x"))
                        y = float(item.get("y"))
                        w = float(item.get("w"))
                        h = float(item.get("h"))
                    except Exception:
                        continue
                    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and 0.0 <= w <= 1.0 and 0.0 <= h <= 1.0):
                        continue
                    if w <= 0.0 or h <= 0.0:
                        continue
                    out.append((x, y, w, h))
                if out:
                    regions = out

        return ImageRemoveWatermarkOptions(
            regions=regions,
            x=_float_opt("x"),
            y=_float_opt("y"),
            w=_float_opt("w"),
            h=_float_opt("h"),
            auto_strength=_int("auto_strength", 40, 10, 120),
            inpaint_radius=_int("inpaint_radius", 3, 1, 12),
            method=("ns" if (form.get("method") == "ns") else "telea"),
            mask_expand=_int("mask_expand", 2, 0, 20),
        )


def _hex_to_rgba(hex_str: str, alpha: float) -> tuple[int, int, int, int]:
    s = hex_str.lstrip("#")
    if len(s) == 3:
        r, g, b = (int(ch * 2, 16) for ch in s)
    else:
        r, g, b = (int(s[i : i + 2], 16) for i in (0, 2, 4))
    return r, g, b, int(max(0.0, min(1.0, alpha)) * 255)


def image_add_text_watermark(image_bytes: bytes, *, text: str, options: ImageTextWatermarkOptions) -> tuple[bytes, str, str]:
    Image = _require_pillow()
    from PIL import ImageDraw

    im = Image.open(io.BytesIO(image_bytes))
    im = im.convert("RGBA")
    width, height = im.size

    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font = _load_font(options.font_size)

    rgba = _hex_to_rgba(options.color_hex, options.opacity)
    shadow_rgb = (255, 255, 255) if _luminance(rgba[:3]) < 0.45 else (0, 0, 0)
    shadow_rgba = (*shadow_rgb, int(min(0.65, options.opacity + 0.18) * 255))
    shadow_offset = max(1, int(options.font_size / 18))

    def _pos_for_single(text_w: int, text_h: int) -> tuple[int, int]:
        m = options.margin
        if options.position == "top_left":
            return m, m
        if options.position == "top_right":
            return width - text_w - m, m
        if options.position == "bottom_left":
            return m, height - text_h - m
        if options.position == "center":
            return (width - text_w) // 2, (height - text_h) // 2
        return width - text_w - m, height - text_h - m

    def _draw_at(x: int, y: int) -> None:
        draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow_rgba)
        draw.text((x, y), text, font=font, fill=rgba)

    if options.style == "single":
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x, y = _pos_for_single(text_w, text_h)
        _draw_at(x, y)
    else:
        step_x = max(160, options.font_size * 5)
        step_y = max(120, options.font_size * 3)
        for y in range(0, height + step_y, step_y):
            for x in range(0, width + step_x, step_x):
                _draw_at(x, y)

    if options.rotation:
        overlay = overlay.rotate(options.rotation, expand=False, resample=Image.Resampling.BICUBIC)

    out = Image.alpha_composite(im, overlay)

    out_rgb = out.convert("RGB")
    fmt = (im.format or "").upper()
    buf = io.BytesIO()
    if fmt in {"JPEG", "JPG"}:
        out_rgb.save(buf, format="JPEG", quality=95, optimize=True)
        return buf.getvalue(), "image/jpeg", ".jpg"
    out_rgb.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), "image/png", ".png"


def image_remove_watermark(image_bytes: bytes, *, options: ImageRemoveWatermarkOptions) -> tuple[bytes, str, str]:
    Image = _require_pillow()
    cv2 = _require_cv2()
    import numpy as np

    im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    width, height = im.size
    arr = np.array(im)
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

    mask = np.zeros((height, width), dtype=np.uint8)

    if options.has_regions:
        for nx, ny, nw, nh in options.regions or []:
            x = int(nx * width)
            y = int(ny * height)
            w = int(nw * width)
            h = int(nh * height)
            x = max(0, min(width - 1, x))
            y = max(0, min(height - 1, y))
            w = max(1, min(width - x, w))
            h = max(1, min(height - y, h))
            mask[y : y + h, x : x + w] = 255
    elif options.has_region:
        x = int((options.x or 0.0) * width)
        y = int((options.y or 0.0) * height)
        w = int((options.w or 0.0) * width)
        h = int((options.h or 0.0) * height)
        x = max(0, min(width - 1, x))
        y = max(0, min(height - 1, y))
        w = max(1, min(width - x, w))
        h = max(1, min(height - y, h))
        mask[y : y + h, x : x + w] = 255
    else:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        blur = cv2.medianBlur(gray, 11)
        diff = cv2.subtract(gray, blur)
        diff2 = cv2.subtract(blur, gray)
        t = max(10, min(80, int(options.auto_strength)))
        _, m1 = cv2.threshold(diff, t, 255, cv2.THRESH_BINARY)
        _, m2 = cv2.threshold(diff2, t, 255, cv2.THRESH_BINARY)
        mask = cv2.bitwise_or(m1, m2)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.dilate(mask, kernel, iterations=1)

        coverage = float(cv2.countNonZero(mask)) / float(width * height) if width > 0 and height > 0 else 1.0
        if coverage > 0.40:
            raise ValueError("自动检测范围过大，建议框选水印区域或降低强度。")

    if options.mask_expand > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (options.mask_expand * 2 + 1, options.mask_expand * 2 + 1))
        mask = cv2.dilate(mask, k, iterations=1)

    method = cv2.INPAINT_NS if options.method == "ns" else cv2.INPAINT_TELEA
    cleaned = cv2.inpaint(bgr, mask, int(options.inpaint_radius), method)
    rgb = cv2.cvtColor(cleaned, cv2.COLOR_BGR2RGB)
    out = Image.fromarray(rgb)

    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), "image/png", ".png"


ImageCompressFormat = Literal["auto", "jpeg", "webp", "png"]


@dataclass(frozen=True)
class ImageCompressOptions:
    crop_x: float | None = None  # normalized 0~1
    crop_y: float | None = None
    crop_w: float | None = None
    crop_h: float | None = None

    out_w_px: int | None = None
    out_h_px: int | None = None

    target_bytes: int | None = None
    fmt: ImageCompressFormat = "auto"

    min_quality: int = 30
    max_quality: int = 95

    preserve_alpha: bool = True
    background_hex: str = "#ffffff"

    @property
    def has_crop(self) -> bool:
        return (
            self.crop_x is not None
            and self.crop_y is not None
            and self.crop_w is not None
            and self.crop_h is not None
            and self.crop_w > 0.0
            and self.crop_h > 0.0
        )

    @staticmethod
    def from_form(form) -> "ImageCompressOptions":
        def _int_opt(name: str, *, min_v: int, max_v: int) -> int | None:
            raw = form.get(name)
            if raw is None or raw == "":
                return None
            try:
                v = int(raw)
            except Exception:
                return None
            return max(min_v, min(max_v, v))

        def _float01_opt(name: str) -> float | None:
            raw = form.get(name)
            if raw is None or raw == "":
                return None
            try:
                v = float(raw)
            except Exception:
                return None
            return max(0.0, min(1.0, v))

        fmt = (form.get("format") or "auto").strip().lower()
        if fmt not in {"auto", "jpeg", "webp", "png"}:
            fmt = "auto"

        preserve_alpha = (form.get("preserve_alpha") or "") in {"1", "true", "on", "yes"}

        background_hex = (form.get("background") or "#ffffff").strip()
        if not background_hex.startswith("#") or len(background_hex) not in {4, 7}:
            background_hex = "#ffffff"

        target_value = _int_opt("target_size", min_v=1, max_v=1000_000)
        target_unit = (form.get("target_unit") or "kb").strip().lower()
        target_bytes = None
        if target_value is not None:
            if target_unit == "mb":
                target_bytes = int(target_value) * 1024 * 1024
            else:
                target_bytes = int(target_value) * 1024

        min_quality = _int_opt("min_quality", min_v=10, max_v=90) or 30
        max_quality = _int_opt("max_quality", min_v=20, max_v=100) or 95
        if min_quality >= max_quality:
            min_quality = max(10, min(90, max_quality - 1))
            max_quality = max(min_quality + 1, max_quality)

        out_w_px = _int_opt("out_w_px", min_v=1, max_v=20000)
        out_h_px = _int_opt("out_h_px", min_v=1, max_v=20000)

        return ImageCompressOptions(
            crop_x=_float01_opt("crop_x"),
            crop_y=_float01_opt("crop_y"),
            crop_w=_float01_opt("crop_w"),
            crop_h=_float01_opt("crop_h"),
            out_w_px=out_w_px,
            out_h_px=out_h_px,
            target_bytes=target_bytes,
            fmt=fmt,  # type: ignore[arg-type]
            min_quality=min_quality,
            max_quality=max_quality,
            preserve_alpha=preserve_alpha,
            background_hex=background_hex,
        )


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    s = hex_str.lstrip("#")
    if len(s) == 3:
        r, g, b = (int(ch * 2, 16) for ch in s)
    else:
        r, g, b = (int(s[i : i + 2], 16) for i in (0, 2, 4))
    return r, g, b


def _has_alpha(im) -> bool:
    if im.mode in {"RGBA", "LA"}:
        return True
    if im.mode == "P":
        return "transparency" in (im.info or {})
    return False


def _choose_format(fmt: ImageCompressFormat, *, has_alpha: bool, pillow_supports_webp: bool) -> ImageCompressFormat:
    if fmt != "auto":
        return fmt
    if has_alpha:
        return "webp" if pillow_supports_webp else "png"
    return "jpeg"


def image_compress(
    image_bytes: bytes,
    *,
    options: ImageCompressOptions,
) -> tuple[bytes, str, str, dict]:
    Image = _require_pillow()
    from PIL import ImageOps, features

    im = Image.open(io.BytesIO(image_bytes))
    im = ImageOps.exif_transpose(im)

    original_w, original_h = im.size
    if original_w <= 0 or original_h <= 0:
        raise ValueError("无效图片尺寸。")
    if original_w * original_h > 120_000_000:
        raise ValueError("图片像素过大，建议先缩小分辨率后再处理。")

    if options.has_crop:
        left = int((options.crop_x or 0.0) * original_w)
        top = int((options.crop_y or 0.0) * original_h)
        w = int((options.crop_w or 0.0) * original_w)
        h = int((options.crop_h or 0.0) * original_h)
        left = max(0, min(original_w - 1, left))
        top = max(0, min(original_h - 1, top))
        w = max(1, min(original_w - left, w))
        h = max(1, min(original_h - top, h))
        im = im.crop((left, top, left + w, top + h))

    if options.out_w_px or options.out_h_px:
        w, h = im.size
        if w <= 0 or h <= 0:
            raise ValueError("无效裁剪尺寸。")
        if options.out_w_px and options.out_h_px:
            target_w, target_h = options.out_w_px, options.out_h_px
        elif options.out_w_px:
            target_w = options.out_w_px
            target_h = max(1, int(round(target_w * (h / w))))
        else:
            target_h = options.out_h_px or h
            target_w = max(1, int(round(target_h * (w / h))))
        if target_w <= 0 or target_h <= 0:
            raise ValueError("输出像素无效。")
        if target_w != w or target_h != h:
            im = im.resize((target_w, target_h), resample=Image.Resampling.LANCZOS)

    had_alpha = _has_alpha(im)
    supports_webp = bool(features.check("webp"))
    fmt = _choose_format(options.fmt, has_alpha=had_alpha and options.preserve_alpha, pillow_supports_webp=supports_webp)

    def _flatten_alpha(src):
        rgba = src.convert("RGBA")
        bg = Image.new("RGB", rgba.size, _hex_to_rgb(options.background_hex))
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg

    def _encode_jpeg(src, *, quality: int) -> bytes:
        if _has_alpha(src):
            src = _flatten_alpha(src)
        else:
            src = src.convert("RGB")
        buf = io.BytesIO()
        src.save(buf, format="JPEG", quality=int(quality), optimize=True, progressive=True)
        return buf.getvalue()

    def _encode_webp(src, *, quality: int) -> bytes:
        buf = io.BytesIO()
        save_kwargs = {"format": "WEBP", "quality": int(quality), "method": 6}
        if _has_alpha(src) and options.preserve_alpha:
            src = src.convert("RGBA")
        elif _has_alpha(src) and not options.preserve_alpha:
            src = _flatten_alpha(src)
        else:
            src = src.convert("RGB")
        src.save(buf, **save_kwargs)
        return buf.getvalue()

    def _encode_png(src) -> bytes:
        buf = io.BytesIO()
        if _has_alpha(src) and options.preserve_alpha:
            src = src.convert("RGBA")
        elif _has_alpha(src) and not options.preserve_alpha:
            src = _flatten_alpha(src)
        else:
            src = src.convert("RGB")
        src.save(buf, format="PNG", optimize=True, compress_level=9)
        return buf.getvalue()

    def _encode_with_quality(src, *, quality: int) -> bytes:
        if fmt == "jpeg":
            return _encode_jpeg(src, quality=quality)
        if fmt == "webp":
            if not supports_webp:
                raise ValueError("当前环境不支持 WebP 输出，请安装带 WebP 支持的 Pillow。")
            return _encode_webp(src, quality=quality)
        raise ValueError("内部错误：不支持的有损格式。")

    def _search_best_quality(src) -> tuple[bytes, int]:
        target = options.target_bytes
        if target is None:
            q = max(82, min(95, options.max_quality))
            return _encode_with_quality(src, quality=q), q

        lo, hi = options.min_quality, options.max_quality
        best_bytes: bytes | None = None
        best_q = lo
        while lo <= hi:
            mid = (lo + hi) // 2
            out_b = _encode_with_quality(src, quality=mid)
            if len(out_b) <= target:
                best_bytes = out_b
                best_q = mid
                lo = mid + 1
            else:
                hi = mid - 1
        if best_bytes is not None:
            return best_bytes, best_q
        q = options.min_quality
        return _encode_with_quality(src, quality=q), q

    out_bytes: bytes
    chosen_quality: int | None = None
    downscaled_steps = 0

    if fmt == "png":
        out_bytes = _encode_png(im)
        if options.target_bytes is not None and len(out_bytes) > options.target_bytes:
            raise ValueError("PNG 很难在保持清晰度的同时精确控大小；建议改用 WebP/JPEG 或降低输出像素。")
        mimetype, suffix = "image/png", ".png"
    else:
        cur = im
        for _ in range(10):
            encoded, q = _search_best_quality(cur)
            chosen_quality = q
            out_bytes = encoded
            if options.target_bytes is None or len(out_bytes) <= options.target_bytes:
                break

            if q > options.min_quality:
                break

            if cur.width <= 320 or cur.height <= 320:
                break

            scale = (float(options.target_bytes) / float(len(out_bytes))) ** 0.5 * 0.95 if options.target_bytes else 0.85
            scale = max(0.35, min(0.92, scale))
            next_w = max(320, int(cur.width * scale))
            next_h = max(320, int(cur.height * scale))
            if next_w == cur.width and next_h == cur.height:
                break
            cur = cur.resize((next_w, next_h), resample=Image.Resampling.LANCZOS)
            downscaled_steps += 1

        if options.target_bytes is not None and len(out_bytes) > options.target_bytes:
            raise ValueError("目标大小过小：已尝试降低质量与分辨率，仍无法满足。建议提高目标大小或降低输出像素。")

        if fmt == "jpeg":
            mimetype, suffix = "image/jpeg", ".jpg"
        else:
            mimetype, suffix = "image/webp", ".webp"

    out_w, out_h = im.size
    if downscaled_steps:
        out_w, out_h = cur.size  # type: ignore[has-type]

    stats = {
        "original_size_bytes": int(len(image_bytes)),
        "output_size_bytes": int(len(out_bytes)),
        "original_w": int(original_w),
        "original_h": int(original_h),
        "output_w": int(out_w),
        "output_h": int(out_h),
        "format": fmt,
        "quality": chosen_quality,
        "downscaled_steps": int(downscaled_steps),
        "had_alpha": bool(had_alpha),
    }
    return out_bytes, mimetype, suffix, stats
