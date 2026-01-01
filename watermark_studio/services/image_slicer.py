from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone

from PIL import Image, ImageOps


class InvalidImageSliceOptionsError(ValueError):
    pass


@dataclass(frozen=True)
class ImageSliceOptions:
    mode: str
    output_format: str  # same|png|jpg|webp

    @classmethod
    def from_form(cls, form) -> "ImageSliceOptions":
        mode = (form.get("mode") or "grid_3").strip().lower()
        if mode not in {"split_v2", "split_h2", "grid_2", "grid_2x3", "grid_3"}:
            mode = "grid_3"

        output_format = (form.get("output_format") or "same").strip().lower()
        if output_format not in {"same", "png", "jpg", "webp"}:
            output_format = "same"

        return cls(mode=mode, output_format=output_format)

    @property
    def rows_cols(self) -> tuple[int, int]:
        if self.mode == "split_v2":
            return 1, 2
        if self.mode == "split_h2":
            return 2, 1
        if self.mode == "grid_2":
            return 2, 2
        if self.mode == "grid_2x3":
            return 2, 3
        return 3, 3


@dataclass(frozen=True)
class SlicedImage:
    filename: str
    payload: bytes
    mimetype: str


def _zip_mtime() -> tuple[int, int, int, int, int, int]:
    dt = datetime.now(timezone.utc).astimezone()
    return (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)


def _guess_original_format(filename: str) -> tuple[str, str, str]:
    lower = (filename or "").lower()
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "jpeg", "image/jpeg", ".jpg"
    if lower.endswith(".webp"):
        return "webp", "image/webp", ".webp"
    if lower.endswith(".png"):
        return "png", "image/png", ".png"
    return "png", "image/png", ".png"


def _normalize_stem(stem: str) -> str:
    stem = (stem or "").strip() or "image"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem)
    stem = re.sub(r"_+", "_", stem).strip("_")
    return stem[:60] if len(stem) > 60 else stem


def _edges(length: int, parts: int) -> list[int]:
    # Use rounded edges to avoid accumulating truncation errors.
    return [round(i * length / parts) for i in range(parts + 1)]


def _encode_image(img: Image.Image, *, output_format: str, original_format: str) -> tuple[bytes, str, str]:
    fmt = output_format
    if fmt == "same":
        fmt = original_format

    if fmt == "jpg":
        fmt = "jpeg"

    if fmt == "jpeg":
        if img.mode in {"RGBA", "LA"}:
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")
        pil_format = "JPEG"
        mimetype = "image/jpeg"
        suffix = ".jpg"
        save_kwargs = {"quality": 100, "subsampling": 0, "optimize": True, "progressive": True}
    elif fmt == "webp":
        pil_format = "WEBP"
        mimetype = "image/webp"
        suffix = ".webp"
        save_kwargs = {"lossless": True, "method": 6, "quality": 100}
    else:
        pil_format = "PNG"
        mimetype = "image/png"
        suffix = ".png"
        save_kwargs = {"optimize": True}

    out = io.BytesIO()
    img.save(out, format=pil_format, **save_kwargs)
    return out.getvalue(), mimetype, suffix


def slice_image(image_bytes: bytes, *, filename: str, options: ImageSliceOptions) -> tuple[list[SlicedImage], bytes]:
    try:
        src = Image.open(io.BytesIO(image_bytes))
        src.load()
        src = ImageOps.exif_transpose(src)
    except Exception as exc:
        raise InvalidImageSliceOptionsError(f"图片无法解析：{exc}") from exc

    original_format, _, _ = _guess_original_format(filename)
    rows, cols = options.rows_cols
    if rows < 1 or cols < 1:
        raise InvalidImageSliceOptionsError("切图参数错误。")

    w, h = src.size
    if w < cols or h < rows:
        raise InvalidImageSliceOptionsError("图片尺寸过小，无法按所选样式切分。")

    xs = _edges(w, cols)
    ys = _edges(h, rows)

    stem = _normalize_stem((filename or "image").rsplit(".", 1)[0])
    sliced: list[SlicedImage] = []

    for r in range(rows):
        for c in range(cols):
            left, right = xs[c], xs[c + 1]
            top, bottom = ys[r], ys[r + 1]
            piece = src.crop((left, top, right, bottom))
            payload, mimetype, suffix = _encode_image(piece, output_format=options.output_format, original_format=original_format)
            idx = r * cols + c + 1
            out_name = f"{stem}_{rows}x{cols}_{idx}{suffix}"
            sliced.append(SlicedImage(filename=out_name, payload=payload, mimetype=mimetype))

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        for item in sliced:
            info = zipfile.ZipInfo(item.filename, date_time=_zip_mtime())
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, item.payload)

    return sliced, zip_buf.getvalue()
