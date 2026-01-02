from __future__ import annotations

import time
from pathlib import Path

from flask import Flask, render_template
from werkzeug.exceptions import RequestEntityTooLarge

from watermark_studio.blueprints.image import image_bp
from watermark_studio.blueprints.main import main_bp
from watermark_studio.blueprints.pdf import pdf_bp
from watermark_studio.blueprints.webapp import webapp_bp


def create_app() -> Flask:
    project_root = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        template_folder=str(project_root / "templates"),
        static_folder=str(project_root / "static"),
        instance_path=str(project_root / "instance"),
    )
    app.config.setdefault("MAX_CONTENT_LENGTH", 50 * 1024 * 1024)  # 50MB
    app.config.setdefault("APP_NAME", "Watermark Studio")
    app.config.setdefault("STATIC_VERSION", str(int(time.time())))

    app.register_blueprint(main_bp)
    app.register_blueprint(pdf_bp, url_prefix="/pdf")
    app.register_blueprint(image_bp, url_prefix="/image")
    app.register_blueprint(webapp_bp, url_prefix="/webapp")

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
