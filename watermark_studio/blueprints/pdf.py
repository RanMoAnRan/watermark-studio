from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from watermark_studio.services.pdf_tools import (
    PdfImageWatermarkOptions,
    PdfTextWatermarkOptions,
    clean_pdf_watermarks,
    compare_pdf_text,
    pdf_add_image_watermark,
    pdf_add_text_watermark,
)
from watermark_studio.services.storage import save_output_bytes
from watermark_studio.utils.files import ensure_image_upload, ensure_pdf_upload

pdf_bp = Blueprint("pdf", __name__)

def _wants_json() -> bool:
    best = request.accept_mimetypes.best or ""
    return best == "application/json" or request.accept_mimetypes["application/json"] >= request.accept_mimetypes["text/html"]


@pdf_bp.get("/remove")
def remove_page():
    return render_template("pdf/remove.html")


@pdf_bp.post("/remove")
def remove_submit():
    try:
        uploaded = ensure_pdf_upload(request.files.get("file"))
        enhanced = request.form.get("enhanced") == "on"
        remove_images = request.form.get("remove_images") == "on"
        result = clean_pdf_watermarks(uploaded.bytes, enhanced=enhanced, remove_image_watermarks=remove_images)
    except Exception as exc:
        if _wants_json():
            return jsonify(ok=False, error=f"处理失败：{exc}"), 400
        return render_template(
            "pdf/remove.html",
            error=f"处理失败：{exc}",
            enhanced=request.form.get("enhanced") == "on",
            remove_images=request.form.get("remove_images") == "on",
        ), 400

    original_name = uploaded.stem + "_original.pdf"
    original_job_id = save_output_bytes(uploaded.bytes, download_name=original_name, mimetype="application/pdf")
    download_name = uploaded.stem + "_cleaned.pdf"
    job_id = save_output_bytes(result.pdf_bytes, download_name=download_name, mimetype="application/pdf")
    text_compare = compare_pdf_text(uploaded.bytes, result.pdf_bytes)

    payload = {
        "ok": True,
        "original_job_id": original_job_id,
        "job_id": job_id,
        "original_preview_url": f"/files/{original_job_id}",
        "original_download_url": f"/files/{original_job_id}?download=1",
        "preview_url": f"/files/{job_id}",
        "download_url": f"/files/{job_id}?download=1",
        "original_name": uploaded.filename,
        "stats": {
            "removed_watermark_annots": result.removed_watermark_annots,
            "removed_watermark_artifacts": result.removed_watermark_artifacts,
            "removed_low_opacity_blocks": result.removed_low_opacity_blocks,
            "removed_suspected_image_xobjects": result.removed_suspected_image_xobjects,
            "text_compare": text_compare,
        },
    }
    if _wants_json():
        return jsonify(payload)

    return render_template(
        "pdf/remove.html",
        original_job_id=original_job_id,
        job_id=job_id,
        original_preview_url=f"/files/{original_job_id}",
        preview_url=f"/files/{job_id}",
        original_download_url=f"/files/{original_job_id}?download=1",
        download_url=f"/files/{job_id}?download=1",
        stats=result,
        text_compare=text_compare,
        enhanced=enhanced,
        remove_images=remove_images,
        original_name=uploaded.filename,
    )


@pdf_bp.get("/add-watermark")
def add_page():
    return render_template("pdf/add_watermark.html")


@pdf_bp.post("/add-watermark")
def add_submit():
    try:
        uploaded = ensure_pdf_upload(request.files.get("file"))
        mode = (request.form.get("mode") or "text").strip().lower()
        if mode not in {"text", "image"}:
            mode = "text"

        if mode == "image":
            wm_upload = ensure_image_upload(request.files.get("watermark_image"))
            img_options = PdfImageWatermarkOptions.from_form(request.form)
            output_bytes = pdf_add_image_watermark(uploaded.bytes, image_bytes=wm_upload.bytes, options=img_options)
        else:
            text = (request.form.get("text") or "").strip()
            if not text:
                raise ValueError("请输入水印文字。")
            options = PdfTextWatermarkOptions.from_form(request.form)
            output_bytes = pdf_add_text_watermark(uploaded.bytes, text=text, options=options)
    except Exception as exc:
        if _wants_json():
            return jsonify(ok=False, error=f"处理失败：{exc}"), 400
        return render_template(
            "pdf/add_watermark.html",
            error=f"处理失败：{exc}",
            mode=request.form.get("mode") or "text",
            text=request.form.get("text") or "",
            options=PdfTextWatermarkOptions.from_form(request.form),
            img_options=PdfImageWatermarkOptions.from_form(request.form),
        ), 400

    download_name = uploaded.stem + "_watermarked.pdf"
    job_id = save_output_bytes(output_bytes, download_name=download_name, mimetype="application/pdf")
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
        "pdf/add_watermark.html",
        job_id=job_id,
        preview_url=f"/files/{job_id}",
        download_url=f"/files/{job_id}?download=1",
        original_name=uploaded.filename,
        mode=mode,
        options=PdfTextWatermarkOptions.from_form(request.form),
        img_options=PdfImageWatermarkOptions.from_form(request.form),
        text=(request.form.get("text") or "").strip(),
    )
