from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from watermark_studio.services.image_tools import (
    ImageRemoveWatermarkOptions,
    ImageTextWatermarkOptions,
    image_add_text_watermark,
    image_remove_watermark,
)
from watermark_studio.services.storage import save_output_bytes
from watermark_studio.utils.files import ensure_image_upload

image_bp = Blueprint("image", __name__)

def _guess_image_mimetype(filename: str) -> tuple[str, str]:
    lower = filename.lower()
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg", ".jpg"
    if lower.endswith(".webp"):
        return "image/webp", ".webp"
    return "image/png", ".png"


def _wants_json() -> bool:
    best = request.accept_mimetypes.best or ""
    return best == "application/json" or request.accept_mimetypes["application/json"] >= request.accept_mimetypes["text/html"]


@image_bp.get("/add-watermark")
def add_page():
    return render_template("image/add_watermark.html")


@image_bp.post("/add-watermark")
def add_submit():
    try:
        uploaded = ensure_image_upload(request.files.get("file"))
        text = (request.form.get("text") or "").strip()
        if not text:
            raise ValueError("请输入水印文字。")

        options = ImageTextWatermarkOptions.from_form(request.form)
        output_bytes, mimetype, suffix = image_add_text_watermark(uploaded.bytes, text=text, options=options)
    except Exception as exc:
        if _wants_json():
            return jsonify(ok=False, error=f"处理失败：{exc}"), 400
        return render_template(
            "image/add_watermark.html",
            error=f"处理失败：{exc}",
            text=request.form.get("text") or "",
            options=ImageTextWatermarkOptions.from_form(request.form),
        ), 400

    original_mimetype, original_suffix = _guess_image_mimetype(uploaded.filename)
    original_name = uploaded.stem + f"_original{original_suffix}"
    original_job_id = save_output_bytes(uploaded.bytes, download_name=original_name, mimetype=original_mimetype)

    download_name = uploaded.stem + f"_watermarked{suffix}"
    job_id = save_output_bytes(output_bytes, download_name=download_name, mimetype=mimetype)
    payload = {
        "ok": True,
        "original_job_id": original_job_id,
        "job_id": job_id,
        "original_preview_url": f"/files/{original_job_id}",
        "original_download_url": f"/files/{original_job_id}?download=1",
        "preview_url": f"/files/{job_id}",
        "download_url": f"/files/{job_id}?download=1",
        "original_name": uploaded.filename,
    }
    if _wants_json():
        return jsonify(payload)

    return render_template(
        "image/add_watermark.html",
        original_job_id=original_job_id,
        job_id=job_id,
        original_preview_url=f"/files/{original_job_id}",
        preview_url=f"/files/{job_id}",
        original_download_url=f"/files/{original_job_id}?download=1",
        download_url=f"/files/{job_id}?download=1",
        original_name=uploaded.filename,
        options=options,
        text=text,
    )


@image_bp.get("/remove-watermark")
def remove_page():
    return render_template("image/remove_watermark.html")


@image_bp.post("/remove-watermark")
def remove_submit():
    try:
        uploaded = ensure_image_upload(request.files.get("file"))
        options = ImageRemoveWatermarkOptions.from_form(request.form)
        output_bytes, mimetype, suffix = image_remove_watermark(uploaded.bytes, options=options)
    except Exception as exc:
        if _wants_json():
            return jsonify(ok=False, error=f"处理失败：{exc}"), 400
        return render_template(
            "image/remove_watermark.html",
            error=f"处理失败：{exc}",
            options=ImageRemoveWatermarkOptions.from_form(request.form),
        ), 400

    download_name = uploaded.stem + f"_cleaned{suffix}"
    job_id = save_output_bytes(output_bytes, download_name=download_name, mimetype=mimetype)
    payload = {
        "ok": True,
        "job_id": job_id,
        "preview_url": f"/files/{job_id}",
        "download_url": f"/files/{job_id}?download=1",
        "original_name": uploaded.filename,
    }
    if _wants_json():
        return jsonify(payload)

    return render_template(
        "image/remove_watermark.html",
        job_id=job_id,
        preview_url=f"/files/{job_id}",
        download_url=f"/files/{job_id}?download=1",
        original_name=uploaded.filename,
        options=options,
    )
