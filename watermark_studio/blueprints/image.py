from __future__ import annotations

import io

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask import send_file

from watermark_studio.services.image_tools import (
    ImageCompressOptions,
    ImageRemoveWatermarkOptions,
    ImageTextWatermarkOptions,
    image_add_text_watermark,
    image_compress,
    image_remove_watermark,
)
from watermark_studio.services.image_composer import ImageComposeOptions, compose_images
from watermark_studio.services.image_slicer import ImageSliceOptions, slice_image
from watermark_studio.services.storage import save_output_bytes
from watermark_studio.utils.files import ensure_image_upload, ensure_image_uploads

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

@image_bp.get("/")
def studio_page():
    tab = (request.args.get("tab") or "").strip().lower()
    if tab not in {"add", "remove"}:
        tab = "add"
    return render_template("image/studio.html", tab=tab)


@image_bp.get("/add-watermark")
def add_page():
    return redirect(url_for("image.studio_page", tab="add"))


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
            "image/studio.html",
            tab="add",
            add_error=f"处理失败：{exc}",
            add_text=request.form.get("text") or "",
            add_options=ImageTextWatermarkOptions.from_form(request.form),
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
        "image/studio.html",
        tab="add",
        add_original_job_id=original_job_id,
        add_job_id=job_id,
        add_original_preview_url=f"/files/{original_job_id}",
        add_preview_url=f"/files/{job_id}",
        add_original_download_url=f"/files/{original_job_id}?download=1",
        add_download_url=f"/files/{job_id}?download=1",
        add_original_name=uploaded.filename,
        add_options=options,
        add_text=text,
    )


@image_bp.get("/remove-watermark")
def remove_page():
    return redirect(url_for("image.studio_page", tab="remove"))


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
            "image/studio.html",
            tab="remove",
            remove_error=f"处理失败：{exc}",
            remove_options=ImageRemoveWatermarkOptions.from_form(request.form),
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
        "image/studio.html",
        tab="remove",
        remove_job_id=job_id,
        remove_preview_url=f"/files/{job_id}",
        remove_download_url=f"/files/{job_id}?download=1",
        remove_original_name=uploaded.filename,
        remove_options=options,
    )


@image_bp.get("/compress")
def compress_page():
    return render_template("image/compress.html")


@image_bp.post("/compress")
def compress_submit():
    try:
        uploaded = ensure_image_upload(request.files.get("file"))
        options = ImageCompressOptions.from_form(request.form)
        output_bytes, mimetype, suffix, stats = image_compress(uploaded.bytes, options=options)
    except Exception as exc:
        if _wants_json():
            return jsonify(ok=False, error=f"处理失败：{exc}"), 400
        return render_template(
            "image/compress.html",
            error=f"处理失败：{exc}",
            options=ImageCompressOptions.from_form(request.form),
        ), 400

    original_mimetype, original_suffix = _guess_image_mimetype(uploaded.filename)
    original_name = uploaded.stem + f"_original{original_suffix}"
    original_job_id = save_output_bytes(uploaded.bytes, download_name=original_name, mimetype=original_mimetype)

    download_name = uploaded.stem + f"_compressed{suffix}"
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
        "stats": stats,
    }
    if _wants_json():
        return jsonify(payload)

    return render_template(
        "image/compress.html",
        original_job_id=original_job_id,
        job_id=job_id,
        original_preview_url=f"/files/{original_job_id}",
        preview_url=f"/files/{job_id}",
        original_download_url=f"/files/{original_job_id}?download=1",
        download_url=f"/files/{job_id}?download=1",
        original_name=uploaded.filename,
        options=options,
        stats=stats,
    )


@image_bp.get("/slice")
def slice_page():
    tab = (request.args.get("tab") or "").strip().lower()
    return render_template("image/slice.html", tab=tab)


@image_bp.post("/slice")
def slice_submit():
    try:
        uploaded = ensure_image_upload(request.files.get("file"))
        options = ImageSliceOptions.from_form(request.form)
        _, zip_bytes = slice_image(uploaded.bytes, filename=uploaded.filename, options=options)
    except Exception as exc:
        if _wants_json():
            return jsonify(ok=False, error=f"处理失败：{exc}"), 400
        return render_template(
            "image/slice.html",
            error=f"处理失败：{exc}",
            options=ImageSliceOptions.from_form(request.form),
            tab="slice",
        ), 400

    rows, cols = options.rows_cols
    zip_name = f"{uploaded.stem}_{rows}x{cols}.zip"
    return send_file(
        io.BytesIO(zip_bytes),
        mimetype="application/zip",
        as_attachment=True,
        download_name=zip_name,
        max_age=0,
    )


@image_bp.post("/compose")
def compose_submit():
    try:
        uploaded_list = ensure_image_uploads(request.files.getlist("files"))
        options = ImageComposeOptions.from_form(request.form)
        out_bytes, mimetype, suffix, meta = compose_images([u.bytes for u in uploaded_list], options=options)
    except Exception as exc:
        if _wants_json():
            return jsonify(ok=False, error=f"处理失败：{exc}"), 400
        return render_template(
            "image/slice.html",
            compose_error=f"处理失败：{exc}",
            tab="compose",
        ), 400

    download_name = uploaded_list[0].stem + f"_compose{suffix}"
    job_id = save_output_bytes(out_bytes, download_name=download_name, mimetype=mimetype)
    payload = {
        "ok": True,
        "job_id": job_id,
        "preview_url": f"/files/{job_id}",
        "download_url": f"/files/{job_id}?download=1",
        "meta": meta,
    }
    if _wants_json():
        return jsonify(payload)

    return render_template(
        "image/slice.html",
        job_id=job_id,
        preview_url=f"/files/{job_id}",
        download_url=f"/files/{job_id}?download=1",
        compose_meta=meta,
        tab="compose",
    )
