from __future__ import annotations

from datetime import datetime, timezone
import secrets

from flask import Blueprint, current_app, jsonify, render_template, request, send_file

from watermark_studio.services.storage import OutputNotFoundError, get_output_file
from watermark_studio.services.tool_registry import (
    add_external_tool,
    delete_external_tool,
    list_external_tools,
    update_external_tool,
)

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    tools = list_external_tools()
    tools_recent = tools[:3]
    tools_dev = [t for t in tools if t.category == "dev"]
    tools_design = [t for t in tools if t.category == "design"]
    tools_other = [t for t in tools if t.category == "other"]
    # Decorative cover image for the "精选工具" block (random placeholder via Lorem Picsum).
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    featured_seed = f"featured-pdf-{today}-{secrets.token_hex(4)}"
    featured_image_url = f"https://picsum.photos/seed/{featured_seed}/960/540"
    return render_template(
        "index.html",
        app_name=current_app.config.get("APP_NAME", "Watermark Studio"),
        external_tools=tools,
        external_tools_recent=tools_recent,
        external_tools_dev=tools_dev,
        external_tools_design=tools_design,
        external_tools_other=tools_other,
        featured_image_url=featured_image_url,
    )


@main_bp.get("/tools/list")
def tools_list():
    tools = list_external_tools()
    return jsonify(
        ok=True,
        tools=[
            {
                "id": t.id,
                "name": t.name,
                "url": t.url,
                "description": t.description,
                "category": t.category,
                "icon": t.icon,
                "created_at": t.created_at,
                "open_new_tab": t.open_new_tab,
            }
            for t in tools
        ],
    )


@main_bp.post("/tools/add")
def tools_add():
    try:
        payload = request.get_json(force=True, silent=False)
        if not isinstance(payload, dict):
            raise ValueError("无效的 JSON。")
        tool = add_external_tool(
            name=str(payload.get("name") or ""),
            url=str(payload.get("url") or ""),
            description=str(payload.get("description") or ""),
            category=str(payload.get("category") or ""),
            icon=str(payload.get("icon") or ""),
            open_new_tab=bool(payload.get("open_new_tab") is not False),
        )
        return jsonify(
            ok=True,
            tool={
                "id": tool.id,
                "name": tool.name,
                "url": tool.url,
                "description": tool.description,
                "category": tool.category,
                "icon": tool.icon,
                "created_at": tool.created_at,
                "open_new_tab": tool.open_new_tab,
            },
        )
    except Exception as exc:
        return jsonify(ok=False, error=f"添加失败：{exc}"), 400


@main_bp.post("/tools/delete/<tool_id>")
def tools_delete(tool_id: str):
    try:
        ok = delete_external_tool(tool_id)
        return jsonify(ok=ok)
    except Exception as exc:
        return jsonify(ok=False, error=f"删除失败：{exc}"), 400


@main_bp.post("/tools/update/<tool_id>")
def tools_update(tool_id: str):
    try:
        payload = request.get_json(force=True, silent=False)
        if not isinstance(payload, dict):
            raise ValueError("无效的 JSON。")
        tool = update_external_tool(
            tool_id,
            name=str(payload.get("name") or ""),
            url=str(payload.get("url") or ""),
            description=str(payload.get("description") or ""),
            category=str(payload.get("category") or ""),
            icon=str(payload.get("icon") or ""),
            open_new_tab=bool(payload.get("open_new_tab") is not False),
        )
        return jsonify(
            ok=True,
            tool={
                "id": tool.id,
                "name": tool.name,
                "url": tool.url,
                "description": tool.description,
                "category": tool.category,
                "icon": tool.icon,
                "created_at": tool.created_at,
                "open_new_tab": tool.open_new_tab,
            },
        )
    except Exception as exc:
        return jsonify(ok=False, error=f"更新失败：{exc}"), 400


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
