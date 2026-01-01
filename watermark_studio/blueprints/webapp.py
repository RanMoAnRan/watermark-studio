from __future__ import annotations

import io

from flask import Blueprint, render_template, request, send_file

from watermark_studio.services.webapp_packager import (
    InvalidWebAppOptionsError,
    WebAppPackageOptions,
    build_capacitor_zip,
    build_pwa_zip,
    normalize_app_id,
    normalize_app_name,
    normalize_target_url,
    normalize_theme_color,
    safe_download_stem,
    suggest_app_id,
    suggest_app_name,
)

webapp_bp = Blueprint("webapp", __name__)


@webapp_bp.get("/")
def pack_page():
    return render_template(
        "webapp/pack.html",
        url="",
        app_name="",
        theme_color="#111827",
        app_id="",
        suggested_app_name="",
        suggested_app_id="",
    )


@webapp_bp.post("/package")
def package_submit():
    raw_url = request.form.get("url") or ""
    raw_app_name = request.form.get("app_name") or ""
    raw_theme_color = request.form.get("theme_color") or ""
    raw_app_id = request.form.get("app_id") or ""
    platform = (request.form.get("platform") or "").strip().lower()
    icon_file = request.files.get("icon")
    icon_bytes = None
    if icon_file and getattr(icon_file, "filename", ""):
        icon_bytes = icon_file.read()
        if not icon_bytes:
            icon_bytes = None

    try:
        target_url = normalize_target_url(raw_url)
        app_name = normalize_app_name(raw_app_name, target_url=target_url)
        theme_color = normalize_theme_color(raw_theme_color)
        app_id = normalize_app_id(raw_app_id, target_url=target_url)
        options = WebAppPackageOptions(
            target_url=target_url,
            app_name=app_name,
            theme_color=theme_color,
            app_id=app_id,
            icon_bytes=icon_bytes,
        )

        stem = safe_download_stem(app_name)
        if platform == "pwa":
            zip_bytes = build_pwa_zip(options)
            download_name = f"{stem}_pwa.zip"
        elif platform in {"android", "ios", "all"}:
            zip_bytes = build_capacitor_zip(options, focus=platform)
            download_name = f"{stem}_{platform}.zip"
        else:
            raise InvalidWebAppOptionsError("请选择打包类型。")

        return send_file(
            io.BytesIO(zip_bytes),
            mimetype="application/zip",
            as_attachment=True,
            download_name=download_name,
            max_age=0,
        )
    except InvalidWebAppOptionsError as exc:
        suggested_app_name = ""
        suggested_app_id = ""
        try:
            if raw_url.strip():
                normalized = normalize_target_url(raw_url)
                suggested_app_name = suggest_app_name(normalized)
                suggested_app_id = suggest_app_id(normalized)
        except Exception:
            pass
        return render_template(
            "webapp/pack.html",
            error=str(exc),
            url=raw_url,
            app_name=raw_app_name,
            theme_color=raw_theme_color or "#111827",
            app_id=raw_app_id,
            suggested_app_name=suggested_app_name,
            suggested_app_id=suggested_app_id,
        ), 400
    except Exception as exc:
        return render_template(
            "webapp/pack.html",
            error=f"打包失败：{exc}",
            url=raw_url,
            app_name=raw_app_name,
            theme_color=raw_theme_color or "#111827",
            app_id=raw_app_id,
            suggested_app_name="",
            suggested_app_id="",
        ), 400
