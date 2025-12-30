from __future__ import annotations

from flask import Blueprint, current_app, render_template, request, send_file

from watermark_studio.services.storage import OutputNotFoundError, get_output_file

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    return render_template("index.html", app_name=current_app.config.get("APP_NAME", "Watermark Studio"))


@main_bp.get("/files/<job_id>")
def files(job_id: str):
    download = request.args.get("download") == "1"
    try:
        output = get_output_file(job_id)
    except OutputNotFoundError:
        return render_template(
            "error.html",
            title="文件不存在",
            message="该预览/下载链接已失效，或文件已被清理。",
        ), 404

    return send_file(
        output.path,
        mimetype=output.mimetype,
        as_attachment=download,
        download_name=output.download_name,
        max_age=0,
    )

