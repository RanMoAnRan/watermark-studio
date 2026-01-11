from __future__ import annotations

import os
import time
import importlib.util
import shutil
import zlib
from pathlib import Path

from flask import Flask, render_template
from werkzeug.exceptions import RequestEntityTooLarge

from watermark_studio.blueprints.image import image_bp
from watermark_studio.blueprints.main import main_bp
from watermark_studio.blueprints.pdf import pdf_bp
from watermark_studio.blueprints.video import video_bp
from watermark_studio.blueprints.webapp import webapp_bp


def _resolve_instance_path(project_root: Path) -> str:
    raw = (os.environ.get("INSTANCE_PATH") or os.environ.get("FLASK_INSTANCE_PATH") or "").strip()
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = project_root / p
        return str(p)

    # Vercel serverless filesystem is read-only except /tmp.
    if (os.environ.get("VERCEL") or "").strip():
        return str(Path("/tmp") / "watermark_studio_instance")

    return str(project_root / "instance")


def create_app() -> Flask:
    project_root = Path(__file__).resolve().parent.parent
    instance_path = _resolve_instance_path(project_root)
    app = Flask(
        __name__,
        template_folder=str(project_root / "templates"),
        static_folder=str(project_root / "static"),
        instance_path=instance_path,
    )
    Path(instance_path).mkdir(parents=True, exist_ok=True)
    app.config.setdefault("MAX_CONTENT_LENGTH", 50 * 1024 * 1024)  # 50MB
    app.config.setdefault("APP_NAME", "Watermark Studio")
    app.config.setdefault("STATIC_VERSION", str(int(time.time())))
    app.config.setdefault("VIDEO_HAVE_FFMPEG", bool(shutil.which("ffmpeg")))
    app.config.setdefault("VIDEO_HAVE_YOUGET", bool(importlib.util.find_spec("you_get")))
    app.config.setdefault("VIDEO_HAVE_YTDLP", bool(importlib.util.find_spec("yt_dlp")))

    app.register_blueprint(main_bp)
    app.register_blueprint(pdf_bp, url_prefix="/pdf")
    app.register_blueprint(image_bp, url_prefix="/image")
    app.register_blueprint(video_bp, url_prefix="/video")
    app.register_blueprint(webapp_bp, url_prefix="/webapp")

    @app.template_filter("icon_hue")
    def _icon_hue(value: object) -> int:
        s = str(value or "").strip()
        if not s:
            return 210
        return int(zlib.crc32(s.encode("utf-8")) % 360)

    @app.context_processor
    def _inject_globals():
        return {
            "app_name": app.config.get("APP_NAME", "Watermark Studio"),
            "static_version": app.config.get("STATIC_VERSION", ""),
        }

    @app.errorhandler(RequestEntityTooLarge)
    def _handle_too_large(_):
        return render_template(
            "error.html",
            title="文件过大",
            message="上传文件超过大小限制（默认 50MB）。",
        ), 413

    return app
