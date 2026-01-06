from __future__ import annotations

import sys

import urllib.parse
import urllib.request
from urllib.parse import urljoin, urlparse

from flask import Blueprint, Response, current_app, jsonify, render_template, request, stream_with_context, url_for

from watermark_studio.services.video_tools import (
    VideoJobError,
    append_log,
    atomic_write_json,
    create_play_session,
    create_task_payload,
    ensure_safe_http_url,
    get_video_job_paths,
    is_youtube_url,
    read_json,
    read_play_session,
    tail_text_file,
)

video_bp = Blueprint("video", __name__)


def _wants_json() -> bool:
    best = request.accept_mimetypes.best or ""
    return best == "application/json" or request.accept_mimetypes["application/json"] >= request.accept_mimetypes["text/html"]


@video_bp.get("/")
def studio_page():
    task_id = (request.args.get("task") or "").strip().lower()
    env = {
        "you_get": bool(current_app.config.get("VIDEO_HAVE_YOUGET")),
        "yt_dlp": bool(current_app.config.get("VIDEO_HAVE_YTDLP")),
        "ffmpeg": bool(current_app.config.get("VIDEO_HAVE_FFMPEG")),
    }
    return render_template("video/studio.html", task_id=task_id or "", env=env)

def _media_kind_from_url(url: str) -> str | None:
    raw = (url or "").strip()
    if not raw:
        return None
    try:
        path = (urlparse(raw).path or "").lower()
    except Exception:
        path = raw.lower()

    if path.endswith(".m3u8"):
        return "hls"
    if path.endswith((".mp4", ".webm", ".mkv", ".mov", ".flv", ".m4a", ".mp3")):
        return "file"
    return None


def _extract_urls_from_text(text: str) -> list[str]:
    urls: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("http://", "https://")):
            urls.append(line.split()[0])
            continue
        # Some you-get outputs wrap URLs in brackets.
        if "http://" in line or "https://" in line:
            for part in line.replace("(", " ").replace(")", " ").replace("[", " ").replace("]", " ").split():
                if part.startswith(("http://", "https://")):
                    urls.append(part)
    # de-dupe preserving order
    seen = set()
    out = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


@video_bp.post("/play/resolve")
def play_resolve():
    try:
        src_url = ensure_safe_http_url(request.form.get("url") or "")
        direct_kind = _media_kind_from_url(src_url)
        resolved_url = ""
        kind = direct_kind or "file"
        if direct_kind:
            resolved_url = src_url
        else:
            import subprocess

            timeout_s = 45

            def try_you_get() -> None:
                nonlocal resolved_url, kind
                if not current_app.config.get("VIDEO_HAVE_YOUGET"):
                    return
                cmd = [sys.executable, "-m", "you_get", "--url", src_url]
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
                out = (p.stdout or "") + "\n" + (p.stderr or "")
                urls = _extract_urls_from_text(out)
                if urls:
                    resolved_url = urls[0]
                    kind = _media_kind_from_url(resolved_url) or "file"

            def try_ytdlp() -> None:
                nonlocal resolved_url, kind
                if not current_app.config.get("VIDEO_HAVE_YTDLP"):
                    return

                # Prefer a single-file format with audio so it can play immediately in browser.
                cmd = [
                    sys.executable,
                    "-m",
                    "yt_dlp",
                    "--no-playlist",
                    "-f",
                    "best[ext=mp4][acodec!=none]/best[acodec!=none]/best",
                    "-g",
                ]

                cookies_from_browser = request.form.get("cookies_from_browser") == "on"
                cookies_browser = (request.form.get("cookies_browser") or "").strip().lower() or "chrome"
                cookies_profile = (request.form.get("cookies_profile") or "").strip()
                cookies_file = request.files.get("cookies_file")
                cookies_file_path = ""
                if cookies_file and getattr(cookies_file, "filename", ""):
                    data = cookies_file.read()
                    if data:
                        from pathlib import Path
                        import os
                        import uuid

                        tmp_dir = Path(current_app.instance_path) / "tmp" / "video_cookies"
                        tmp_dir.mkdir(parents=True, exist_ok=True)
                        p = tmp_dir / f"play_{uuid.uuid4().hex}.cookies.txt"
                        p.write_bytes(data)
                        try:
                            os.chmod(p, 0o600)
                        except Exception:
                            pass
                        cookies_file_path = str(p)

                if cookies_file_path:
                    cmd += ["--cookies", cookies_file_path]
                elif cookies_from_browser:
                    browser_arg = cookies_browser
                    if cookies_profile:
                        browser_arg = f"{cookies_browser}:{cookies_profile}"
                    cmd += ["--cookies-from-browser", browser_arg]

                cmd.append(src_url)
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
                out = (p.stdout or "") + "\n" + (p.stderr or "")
                if "sign in to confirm you" in out.lower() or "not a bot" in out.lower():
                    raise VideoJobError("YouTube 要求验证“你不是机器人”。请在页面中启用 Cookies（从浏览器读取或上传 cookies.txt）后重试。")
                if "cookies-from-browser" in out.lower() and "error" in out.lower() and "cookie" in out.lower():
                    raise VideoJobError("读取浏览器 Cookies 失败：请尝试填写 Profile 名称或改用上传 cookies.txt。")
                urls = _extract_urls_from_text(out)
                if urls:
                    resolved_url = urls[0]
                    kind = _media_kind_from_url(resolved_url) or "file"

            try:
                # For YouTube, yt-dlp is the primary resolver; you-get is often outdated.
                if is_youtube_url(src_url):
                    if not current_app.config.get("VIDEO_HAVE_YTDLP"):
                        raise VideoJobError("YouTube 解析播放需要安装 yt-dlp；或改用“开始下载”。")
                    try_ytdlp()
                else:
                    # For other sites (e.g. v.qq.com), prefer you-get first; yt-dlp may be slower/hang.
                    try_you_get()
                    if not resolved_url:
                        try_ytdlp()
            except subprocess.TimeoutExpired:
                raise VideoJobError(f"解析超时（>{timeout_s}s）：该站点解析较慢；可稍后重试或使用“开始下载”。")

            if not resolved_url:
                raise VideoJobError("解析失败：未获取到可播放直链；可尝试“开始下载”。")

        token = create_play_session(source_url=src_url, media_url=resolved_url, kind=kind, ttl_seconds=60 * 30)

        play_url = url_for("video.play_proxy", token=token)
        hls_url = url_for("video.hls_index", token=token)
        return jsonify(ok=True, token=token, kind=kind, play_url=play_url, hls_url=hls_url, media_url=resolved_url)
    except VideoJobError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    except Exception as exc:
        return jsonify(ok=False, error=f"解析失败：{exc}"), 500


def _proxy_stream(upstream_url: str, *, referer: str, range_header: str | None) -> Response:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Accept": "*/*",
        "Referer": referer,
    }
    if range_header:
        headers["Range"] = range_header

    req = urllib.request.Request(upstream_url, headers=headers, method="GET")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
    except Exception as exc:
        return Response(f"Upstream fetch failed: {exc}", status=502, mimetype="text/plain")

    status = getattr(resp, "status", 200)
    upstream_headers = dict(getattr(resp, "headers", {}) or {})
    content_type = upstream_headers.get("Content-Type") or "application/octet-stream"
    content_length = upstream_headers.get("Content-Length")
    content_range = upstream_headers.get("Content-Range")
    accept_ranges = upstream_headers.get("Accept-Ranges") or "bytes"

    def gen():
        with resp:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    out = Response(stream_with_context(gen()), status=status, mimetype=content_type)
    if content_length:
        out.headers["Content-Length"] = content_length
    if content_range:
        out.headers["Content-Range"] = content_range
    if accept_ranges:
        out.headers["Accept-Ranges"] = accept_ranges
    out.headers["Cache-Control"] = "no-store"
    return out


@video_bp.get("/play/<token>")
def play_proxy(token: str):
    try:
        sess = read_play_session(token)
        base_media = sess.get("media_url") or ""
        src = sess.get("source_url") or ""
        target = request.args.get("u") or ""
        if target:
            target = urllib.parse.unquote(target)
        upstream = target or base_media
        upstream = ensure_safe_http_url(upstream)
        range_header = request.headers.get("Range")
        return _proxy_stream(upstream, referer=src, range_header=range_header)
    except VideoJobError as exc:
        return Response(str(exc), status=400, mimetype="text/plain")
    except Exception as exc:
        return Response(f"Proxy error: {exc}", status=500, mimetype="text/plain")


@video_bp.get("/hls/<token>/index.m3u8")
def hls_index(token: str):
    try:
        sess = read_play_session(token)
        if (sess.get("kind") or "") != "hls":
            return Response("Not an HLS session.", status=400, mimetype="text/plain")

        playlist_url = ensure_safe_http_url(sess.get("media_url") or "")
        src = sess.get("source_url") or ""

        req = urllib.request.Request(
            playlist_url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "*/*",
                "Referer": src,
            },
            method="GET",
        )
        resp = urllib.request.urlopen(req, timeout=20)
        raw = resp.read()
        text = raw.decode("utf-8", errors="replace")

        base = playlist_url
        rewritten: list[str] = []
        for line in text.splitlines():
            s = line.strip()
            if not s:
                rewritten.append(line)
                continue
            if s.startswith("#"):
                # Rewrite HLS KEY URIs.
                if "URI=\"" in line:
                    prefix, rest = line.split("URI=\"", 1)
                    uri, suffix = rest.split("\"", 1) if "\"" in rest else (rest, "")
                    abs_u = urljoin(base, uri)
                    proxied = url_for("video.play_proxy", token=token) + "?u=" + urllib.parse.quote(abs_u, safe="")
                    rewritten.append(prefix + "URI=\"" + proxied + "\"" + suffix)
                else:
                    rewritten.append(line)
                continue

            abs_u = urljoin(base, s)
            proxied = url_for("video.play_proxy", token=token) + "?u=" + urllib.parse.quote(abs_u, safe="")
            rewritten.append(proxied)

        out = "\n".join(rewritten) + "\n"
        return Response(out, status=200, mimetype="application/vnd.apple.mpegurl")
    except VideoJobError as exc:
        return Response(str(exc), status=400, mimetype="text/plain")
    except Exception as exc:
        return Response(f"HLS error: {exc}", status=500, mimetype="text/plain")


@video_bp.post("/download")
def download_submit():
    try:
        url = ensure_safe_http_url(request.form.get("url") or "")
        playlist = request.form.get("playlist") == "on"
        subtitles = request.form.get("subtitles") == "on"
        cover = request.form.get("cover") == "on"

        if is_youtube_url(url) and not current_app.config.get("VIDEO_HAVE_YTDLP"):
            raise VideoJobError("YouTube 下载建议安装 yt-dlp（you-get 可能已失效）。")

        task = create_task_payload(url=url, playlist=playlist, subtitles=subtitles, cover=cover)
        paths = get_video_job_paths(task["task_id"])
        atomic_write_json(paths.task_json, task)
        append_log(paths.task_log, f"[queued] {url}")

        cookies_from_browser = request.form.get("cookies_from_browser") == "on"
        cookies_browser = (request.form.get("cookies_browser") or "").strip().lower() or "chrome"
        cookies_profile = (request.form.get("cookies_profile") or "").strip()
        cookies_file = request.files.get("cookies_file")
        cookies_file_path = ""
        if cookies_file and getattr(cookies_file, "filename", ""):
            data = cookies_file.read()
            if data:
                from pathlib import Path
                import os

                tmp_dir = Path(current_app.instance_path) / "tmp" / "video_cookies"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                p = tmp_dir / f"{task['task_id']}.cookies.txt"
                p.write_bytes(data)
                try:
                    os.chmod(p, 0o600)
                except Exception:
                    pass
                cookies_file_path = str(p)

        task["cookies"] = {
            "from_browser": bool(cookies_from_browser),
            "browser": cookies_browser,
            "profile": cookies_profile,
            "file_path": cookies_file_path,
        }
        atomic_write_json(paths.task_json, task)

        worker = [
            sys.executable,
            "-m",
            "watermark_studio.workers.video_job",
            task["task_id"],
        ]
        # Start detached worker; it will update task files.
        import subprocess

        p = subprocess.Popen(worker, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        task["worker_pid"] = p.pid
        atomic_write_json(paths.task_json, task)
    except VideoJobError as exc:
        if _wants_json():
            return jsonify(ok=False, error=str(exc)), 400
        return render_template("video/studio.html", error=str(exc)), 400
    except Exception as exc:
        if _wants_json():
            return jsonify(ok=False, error=f"启动失败：{exc}"), 500
        return render_template("video/studio.html", error=f"启动失败：{exc}"), 500

    return jsonify(
        ok=True,
        task_id=task["task_id"],
        task_url=url_for("video.task_status", task_id=task["task_id"]),
    )


@video_bp.get("/tasks/<task_id>")
def task_status(task_id: str):
    try:
        paths = get_video_job_paths(task_id)
        task = read_json(paths.task_json)
        log_tail = tail_text_file(paths.task_log, max_lines=220)

        results = task.get("results") or {}
        files = results.get("files") or []
        for f in files:
            job_id = (f.get("job_id") or "").strip()
            if job_id:
                f["download_url"] = f"/files/{job_id}?download=1"
                f["preview_url"] = f"/files/{job_id}"

        zip_job_id = results.get("zip_job_id")
        zip_download_url = f"/files/{zip_job_id}?download=1" if zip_job_id else ""
    except VideoJobError as exc:
        return jsonify(ok=False, error=str(exc)), 404
    except Exception as exc:
        return jsonify(ok=False, error=f"读取任务失败：{exc}"), 500

    return jsonify(
        ok=True,
        task=task,
        log_tail=log_tail,
        zip_download_url=zip_download_url,
    )
