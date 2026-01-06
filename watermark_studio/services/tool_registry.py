from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from flask import current_app


@dataclass(frozen=True)
class ExternalTool:
    id: str
    name: str
    url: str
    description: str
    category: str  # "dev" | "design" | "other"
    icon: str
    created_at: int
    open_new_tab: bool


def _tools_path() -> Path:
    project_root = Path(current_app.root_path).resolve().parent
    raw = (os.environ.get("TOOLS_JSON_PATH") or "").strip()
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = project_root / p
    else:
        p = project_root / "data" / "tools.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _normalize_category(raw: str) -> str:
    c = (raw or "").strip().lower()
    if c in {"dev", "design", "other"}:
        return c
    return "other"


def _safe_icon(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return "🔗"
    return s[:2]


def _read_doc(path: Path) -> dict:
    if not path.exists():
        return {"schema": "watermark-studio.tools-v1", "tools": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema": "watermark-studio.tools-v1", "tools": []}
    if not isinstance(data, dict):
        return {"schema": "watermark-studio.tools-v1", "tools": []}
    if not isinstance(data.get("tools"), list):
        data["tools"] = []
    data.setdefault("schema", "watermark-studio.tools-v1")
    return data


def _atomic_write(path: Path, payload: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def list_external_tools(*, limit: int | None = None) -> list[ExternalTool]:
    path = _tools_path()
    doc = _read_doc(path)
    out: list[ExternalTool] = []
    for row in doc.get("tools", []):
        if not isinstance(row, dict):
            continue
        try:
            out.append(
                ExternalTool(
                    id=str(row.get("id") or ""),
                    name=str(row.get("name") or ""),
                    url=str(row.get("url") or ""),
                    description=str(row.get("description") or ""),
                    category=_normalize_category(str(row.get("category") or "")),
                    icon=_safe_icon(str(row.get("icon") or "")),
                    created_at=int(row.get("created_at") or 0),
                    open_new_tab=bool(row.get("open_new_tab") is True),
                )
            )
        except Exception:
            continue

    out.sort(key=lambda x: x.created_at, reverse=True)
    if limit is not None:
        return out[: max(0, int(limit))]
    return out


def add_external_tool(
    *,
    name: str,
    url: str,
    description: str = "",
    category: str = "other",
    icon: str = "🔗",
    open_new_tab: bool = True,
) -> ExternalTool:
    n = (name or "").strip()
    u = (url or "").strip()
    if not n:
        raise ValueError("请输入工具名称。")
    if not u:
        raise ValueError("请输入外链地址。")
    if not (u.startswith("http://") or u.startswith("https://")):
        raise ValueError("外链地址仅支持 http:// 或 https:// 开头。")

    tool = ExternalTool(
        id=uuid.uuid4().hex,
        name=n,
        url=u,
        description=(description or "").strip(),
        category=_normalize_category(category),
        icon=_safe_icon(icon),
        created_at=int(time.time()),
        open_new_tab=bool(open_new_tab),
    )

    path = _tools_path()
    doc = _read_doc(path)
    tools = [t for t in doc.get("tools", []) if isinstance(t, dict)]
    tools.append(
        {
            "id": tool.id,
            "name": tool.name,
            "url": tool.url,
            "description": tool.description,
            "category": tool.category,
            "icon": tool.icon,
            "created_at": tool.created_at,
            "open_new_tab": tool.open_new_tab,
        }
    )
    doc["tools"] = tools
    _atomic_write(path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    return tool


def delete_external_tool(tool_id: str) -> bool:
    tid = (tool_id or "").strip()
    if not tid:
        return False
    path = _tools_path()
    doc = _read_doc(path)
    tools = [t for t in doc.get("tools", []) if isinstance(t, dict)]
    kept = [t for t in tools if str(t.get("id") or "") != tid]
    if len(kept) == len(tools):
        return False
    doc["tools"] = kept
    _atomic_write(path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    return True


def update_external_tool(
    tool_id: str,
    *,
    name: str,
    url: str,
    description: str = "",
    category: str = "other",
    icon: str = "🔗",
    open_new_tab: bool = True,
) -> ExternalTool:
    tid = (tool_id or "").strip()
    if not tid:
        raise ValueError("无效的工具 ID。")

    n = (name or "").strip()
    u = (url or "").strip()
    if not n:
        raise ValueError("请输入工具名称。")
    if not u:
        raise ValueError("请输入外链地址。")
    if not (u.startswith("http://") or u.startswith("https://")):
        raise ValueError("外链地址仅支持 http:// 或 https:// 开头。")

    path = _tools_path()
    doc = _read_doc(path)
    tools = [t for t in doc.get("tools", []) if isinstance(t, dict)]

    found: dict | None = None
    for t in tools:
        if str(t.get("id") or "") == tid:
            found = t
            break
    if not found:
        raise ValueError("外链工具不存在或已被删除。")

    found["name"] = n
    found["url"] = u
    found["description"] = (description or "").strip()
    found["category"] = _normalize_category(category)
    found["icon"] = _safe_icon(icon)
    found["open_new_tab"] = bool(open_new_tab)
    if not isinstance(found.get("created_at"), int) or int(found.get("created_at") or 0) <= 0:
        found["created_at"] = int(time.time())

    doc["tools"] = tools
    _atomic_write(path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")

    return ExternalTool(
        id=str(found.get("id") or ""),
        name=str(found.get("name") or ""),
        url=str(found.get("url") or ""),
        description=str(found.get("description") or ""),
        category=_normalize_category(str(found.get("category") or "")),
        icon=_safe_icon(str(found.get("icon") or "")),
        created_at=int(found.get("created_at") or 0),
        open_new_tab=bool(found.get("open_new_tab") is True),
    )
