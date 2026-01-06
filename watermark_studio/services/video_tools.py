from __future__ import annotations

import ipaddress
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from flask import current_app


class VideoJobError(Exception):
    pass


@dataclass(frozen=True)
class VideoJobPaths:
    job_dir: Path
    task_json: Path
    task_log: Path


def _video_jobs_dir() -> Path:
    instance_path = Path(current_app.instance_path)
    d = instance_path / "video_jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _video_tmp_root() -> Path:
    instance_path = Path(current_app.instance_path)
    d = instance_path / "tmp" / "video"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _video_play_dir() -> Path:
    instance_path = Path(current_app.instance_path)
    d = instance_path / "video_play"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_video_job_paths(task_id: str) -> VideoJobPaths:
    if not task_id or any(c not in "0123456789abcdef" for c in task_id.lower()):
        raise VideoJobError("Invalid task id.")
    base = _video_jobs_dir().resolve()
    task_json = (base / f"{task_id}.json").resolve()
    task_log = (base / f"{task_id}.log").resolve()
    if task_json.parent != base or task_log.parent != base:
        raise VideoJobError("Invalid task id.")
    return VideoJobPaths(job_dir=base, task_json=task_json, task_log=task_log)


def new_task_id() -> str:
    return uuid.uuid4().hex


def new_play_token() -> str:
    return uuid.uuid4().hex


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise VideoJobError("Task not found.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise VideoJobError(f"Corrupted task file: {exc}") from exc


def append_log(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", errors="replace") as f:
        f.write(line.rstrip("\n") + "\n")


def tail_text_file(path: Path, *, max_lines: int = 200, max_bytes: int = 64 * 1024) -> list[str]:
    if not path.exists():
        return []
    try:
        size = path.stat().st_size
        start = max(0, size - max_bytes)
        with path.open("rb") as f:
            f.seek(start)
            chunk = f.read()
        text = chunk.decode("utf-8", errors="replace")
        lines = text.splitlines()
        return lines[-max_lines:]
    except Exception:
        return []


def ensure_safe_http_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url:
        raise VideoJobError("请输入视频链接。")

    p = urlparse(url)
    if p.scheme not in {"http", "https"}:
        raise VideoJobError("仅支持 http/https 链接。")
    if not p.netloc:
        raise VideoJobError("无效的链接。")

    hostname = p.hostname or ""
    if not hostname:
        raise VideoJobError("无效的链接。")
    if hostname.lower() in {"localhost"} or hostname.lower().endswith(".local"):
        raise VideoJobError("不支持本机/内网地址。")

    # If it's a literal IP, block private/local ranges. For domain names, do not
    # resolve DNS here to avoid false positives in user environments (e.g. DNS
    # sinkholes mapping domains to 0.0.0.0/127.0.0.1).
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise VideoJobError("不支持本机/内网地址。")
    except ValueError:
        pass

    return url


def is_youtube_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    return host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}


def get_play_session_path(token: str) -> Path:
    t = (token or "").strip().lower()
    if not t or any(c not in "0123456789abcdef" for c in t):
        raise VideoJobError("Invalid token.")
    base = _video_play_dir().resolve()
    p = (base / f"{t}.json").resolve()
    if p.parent != base:
        raise VideoJobError("Invalid token.")
    return p


def create_play_session(*, source_url: str, media_url: str, kind: str, ttl_seconds: int = 60 * 30) -> str:
    src = ensure_safe_http_url(source_url)
    media = ensure_safe_http_url(media_url)
    k = (kind or "").strip().lower()
    if k not in {"file", "hls"}:
        k = "file"

    token = new_play_token()
    now = int(time.time())
    payload: dict[str, Any] = {
        "token": token,
        "created_at": now,
        "expires_at": now + int(ttl_seconds),
        "source_url": src,
        "media_url": media,
        "kind": k,
    }
    atomic_write_json(get_play_session_path(token), payload)
    return token


def read_play_session(token: str) -> dict[str, Any]:
    p = get_play_session_path(token)
    sess = read_json(p)
    now = int(time.time())
    exp = int(sess.get("expires_at") or 0)
    if exp and now > exp:
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
        raise VideoJobError("播放链接已过期，请重新解析。")
    return sess


def create_task_payload(*, url: str, playlist: bool, subtitles: bool, cover: bool) -> dict[str, Any]:
    return {
        "task_id": new_task_id(),
        "created_at": int(time.time()),
        "url": url,
        "options": {"playlist": bool(playlist), "subtitles": bool(subtitles), "cover": bool(cover)},
        "status": "queued",
        "progress": {},
        "results": {"files": [], "zip_job_id": None},
        "error": None,
    }


def create_tmp_dir(task_id: str) -> Path:
    root = _video_tmp_root().resolve()
    d = (root / task_id).resolve()
    if d.parent != root:
        raise VideoJobError("Invalid task id.")
    d.mkdir(parents=True, exist_ok=True)
    return d


def guess_mimetype(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".mp4"):
        return "video/mp4"
    if lower.endswith(".webm"):
        return "video/webm"
    if lower.endswith(".mkv"):
        return "video/x-matroska"
    if lower.endswith(".mov"):
        return "video/quicktime"
    if lower.endswith(".flv"):
        return "video/x-flv"
    if lower.endswith(".m4a"):
        return "audio/mp4"
    if lower.endswith(".mp3"):
        return "audio/mpeg"
    if lower.endswith(".srt"):
        return "application/x-subrip"
    if lower.endswith(".ass") or lower.endswith(".ssa"):
        return "text/plain"
    if lower.endswith(".vtt"):
        return "text/vtt"
    if lower.endswith(".lrc"):
        return "text/plain"
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".zip"):
        return "application/zip"
    return "application/octet-stream"


def classify_kind(path: Path) -> str | None:
    lower = path.name.lower()
    if lower.endswith((".srt", ".ass", ".ssa", ".vtt", ".lrc")):
        return "subtitle"
    if lower.endswith((".jpg", ".jpeg", ".png", ".webp")):
        return "cover"
    if lower.endswith((".mp4", ".mkv", ".webm", ".mov", ".flv", ".m4a", ".mp3")):
        return "video"
    return None


def iter_output_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        name = p.name.lower()
        if name.endswith((".part", ".tmp", ".download")):
            continue
        if name == ".ds_store":
            continue
        kind = classify_kind(p)
        if kind:
            files.append(p)
    files.sort(key=lambda x: x.as_posix())
    return files


def safe_rel_name(root: Path, path: Path) -> str:
    try:
        rel = path.relative_to(root)
        s = rel.as_posix()
    except Exception:
        s = path.name
    s = s.replace("\\", "/")
    # Avoid zip-slip: keep it relative and strip dangerous segments.
    parts = [p for p in s.split("/") if p not in {"", ".", ".."}]
    return "/".join(parts) or path.name


def is_process_alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False
