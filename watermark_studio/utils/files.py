from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class UploadedFile:
    filename: str
    stem: str
    bytes: bytes


def _safe_stem(filename: str) -> str:
    base = os.path.basename(filename).strip()
    if "." in base:
        base = base.rsplit(".", 1)[0]
    base = "".join(ch for ch in base if ch.isalnum() or ch in {"-", "_"})
    return base or "file"


def ensure_pdf_upload(file_storage) -> UploadedFile:
    if file_storage is None or not getattr(file_storage, "filename", ""):
        raise ValueError("请选择一个 PDF 文件。")
    filename = str(file_storage.filename)
    if not filename.lower().endswith(".pdf"):
        raise ValueError("仅支持 PDF 文件。")
    payload = file_storage.stream.read()
    if not payload.startswith(b"%PDF"):
        raise ValueError("不是有效的 PDF 文件。")
    return UploadedFile(filename=filename, stem=_safe_stem(filename), bytes=payload)


def ensure_image_upload(file_storage) -> UploadedFile:
    if file_storage is None or not getattr(file_storage, "filename", ""):
        raise ValueError("请选择一个图片文件。")
    filename = str(file_storage.filename)
    lower = filename.lower()
    if not (lower.endswith(".png") or lower.endswith(".jpg") or lower.endswith(".jpeg") or lower.endswith(".webp")):
        raise ValueError("仅支持 PNG/JPG/WEBP 图片。")
    payload = file_storage.stream.read()
    if not payload:
        raise ValueError("空文件。")
    return UploadedFile(filename=filename, stem=_safe_stem(filename), bytes=payload)

