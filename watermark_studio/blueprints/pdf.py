from __future__ import annotations

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from watermark_studio.services.pdf_tools import (
    PdfImageWatermarkOptions,
    PdfTextWatermarkOptions,
    clean_pdf_watermarks,
    compare_pdf_text,
    pdf_add_image_watermark,
    pdf_add_text_watermark,
)
from watermark_studio.services.storage import OutputNotFoundError, get_output_file, save_output_bytes
from watermark_studio.utils.files import ensure_image_upload, ensure_pdf_upload

pdf_bp = Blueprint("pdf", __name__)

def _wants_json() -> bool:
    best = request.accept_mimetypes.best or ""
    return best == "application/json" or request.accept_mimetypes["application/json"] >= request.accept_mimetypes["text/html"]

def _viewer_url_add(job_id: str) -> str:
    return url_for("pdf.view_add_job", job_id=job_id)


def _viewer_url_remove(job_id: str) -> str:
    return url_for("pdf.view_remove_job", job_id=job_id)


def _parse_intent(default: str = "display") -> str:
    intent = (request.args.get("intent") or "").strip().lower()
    if intent == "print":
        return "print"
    if intent == "display":
        return "display"
    return "print" if default == "print" else "display"


def _render_viewer_for_job(job_id: str, *, intent_default: str) -> tuple[str, int] | str:
    page_raw = (request.args.get("page") or "").strip()
    try:
        page = int(page_raw) if page_raw else 1
    except ValueError:
        page = 1
    page = max(1, page)

    intent = _parse_intent(intent_default)
    try:
        output = get_output_file(job_id)
    except OutputNotFoundError:
        return (
            render_template(
                "error.html",
                title="文件不存在",
                message="该预览/下载链接已失效，或文件已被清理。",
            ),
            404,
        )

    return render_template(
        "pdf/viewer.html",
        file_url=f"/files/{output.job_id}",
        page=page,
        download_name=output.download_name,
        intent=intent,
    )


@pdf_bp.get("/viewer")
def viewer():
    file_url = (request.args.get("file") or "").strip()
    page_raw = (request.args.get("page") or "").strip()
    try:
        page = int(page_raw) if page_raw else 1
    except ValueError:
        page = 1
    page = max(1, page)

    if not file_url.startswith("/files/"):
        return render_template(
            "error.html",
            title="预览不可用",
            message="无效的预览地址。",
        ), 400

    intent = _parse_intent("display")
    download_name = ""
    try:
        job_id = file_url.removeprefix("/files/").strip()
        if job_id:
            download_name = get_output_file(job_id).download_name
    except Exception:
        download_name = ""

    return render_template(
        "pdf/viewer.html",
        file_url=file_url,
        page=page,
        download_name=download_name,
        intent=intent,
    )


@pdf_bp.get("/view/<job_id>")
def view_job(job_id: str):
    return _render_viewer_for_job(job_id, intent_default="display")


@pdf_bp.get("/view-add/<job_id>")
def view_add_job(job_id: str):
    return _render_viewer_for_job(job_id, intent_default="display")


@pdf_bp.get("/view-remove/<job_id>")
def view_remove_job(job_id: str):
    return _render_viewer_for_job(job_id, intent_default="print")

@pdf_bp.get("/")
def studio_page():
    tab = (request.args.get("tab") or "").strip().lower()
    if tab not in {"remove", "add"}:
        tab = "remove"
    return render_template("pdf/studio.html", tab=tab)


@pdf_bp.get("/remove")
def remove_page():
    return redirect(url_for("pdf.studio_page", tab="remove"))


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
            "pdf/studio.html",
            tab="remove",
            remove_error=f"处理失败：{exc}",
            remove_enhanced=request.form.get("enhanced") == "on",
            remove_remove_images=request.form.get("remove_images") == "on",
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
        "original_viewer_url": _viewer_url_remove(original_job_id),
        "preview_url": f"/files/{job_id}",
        "download_url": f"/files/{job_id}?download=1",
        "viewer_url": _viewer_url_remove(job_id),
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
        "pdf/studio.html",
        tab="remove",
        remove_original_job_id=original_job_id,
        remove_job_id=job_id,
        remove_preview_url=f"/files/{job_id}",
        remove_original_download_url=f"/files/{original_job_id}?download=1",
        remove_download_url=f"/files/{job_id}?download=1",
        remove_stats=result,
        remove_text_compare=text_compare,
        remove_enhanced=enhanced,
        remove_remove_images=remove_images,
        remove_original_name=uploaded.filename,
    )


@pdf_bp.get("/add-watermark")
def add_page():
    return redirect(url_for("pdf.studio_page", tab="add"))


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
            "pdf/studio.html",
            tab="add",
            add_error=f"处理失败：{exc}",
            add_mode=request.form.get("mode") or "text",
            add_text=request.form.get("text") or "",
            add_options=PdfTextWatermarkOptions.from_form(request.form),
            add_img_options=PdfImageWatermarkOptions.from_form(request.form),
        ), 400

    original_name = uploaded.stem + "_original.pdf"
    original_job_id = save_output_bytes(uploaded.bytes, download_name=original_name, mimetype="application/pdf")
    download_name = uploaded.stem + "_watermarked.pdf"
    job_id = save_output_bytes(output_bytes, download_name=download_name, mimetype="application/pdf")
    payload = {
        "ok": True,
        "original_job_id": original_job_id,
        "job_id": job_id,
        "original_preview_url": f"/files/{original_job_id}",
        "original_download_url": f"/files/{original_job_id}?download=1",
        "original_viewer_url": _viewer_url_add(original_job_id),
        "preview_url": f"/files/{job_id}",
        "download_url": f"/files/{job_id}?download=1",
        "viewer_url": _viewer_url_add(job_id),
        "original_name": uploaded.filename,
    }
    if _wants_json():
        return jsonify(payload)

    return render_template(
        "pdf/studio.html",
        tab="add",
        add_original_job_id=original_job_id,
        add_job_id=job_id,
        add_preview_url=f"/files/{job_id}",
        add_original_download_url=f"/files/{original_job_id}?download=1",
        add_download_url=f"/files/{job_id}?download=1",
        add_original_name=uploaded.filename,
        add_mode=mode,
        add_options=PdfTextWatermarkOptions.from_form(request.form),
        add_img_options=PdfImageWatermarkOptions.from_form(request.form),
        add_text=(request.form.get("text") or "").strip(),
    )
