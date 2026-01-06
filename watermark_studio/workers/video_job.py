from __future__ import annotations

import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from watermark_studio import create_app
from watermark_studio.services.storage import save_output_file
from watermark_studio.services.video_tools import (
    VideoJobError,
    append_log,
    atomic_write_json,
    classify_kind,
    create_tmp_dir,
    get_video_job_paths,
    guess_mimetype,
    iter_output_files,
    read_json,
    safe_rel_name,
)


def _you_get_cmd() -> list[str]:
    return [sys.executable, "-m", "you_get"]

def _yt_dlp_cmd() -> list[str]:
    return [sys.executable, "-m", "yt_dlp"]


def _is_youtube(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    return host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}


def _detect_you_get_caps() -> dict[str, bool]:
    try:
        p = subprocess.run(
            _you_get_cmd() + ["--help"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        out = (p.stdout or "") + "\n" + (p.stderr or "")
    except Exception:
        out = ""
    return {
        "playlist": "--playlist" in out,
        "caption": "--caption" in out,
        "subtitles": "--subtitles" in out,
        "subtitle": "--subtitle" in out,
    }


def _build_download_cmd(url: str, *, out_dir: Path, playlist: bool, subtitles: bool, cover: bool) -> list[str]:
    caps = _detect_you_get_caps()
    cmd = _you_get_cmd() + ["-o", str(out_dir)]
    if playlist and caps.get("playlist"):
        cmd.append("--playlist")
    if subtitles:
        if caps.get("caption"):
            cmd.append("--caption")
        elif caps.get("subtitles"):
            cmd.append("--subtitles")
        elif caps.get("subtitle"):
            cmd.append("--subtitle")
    # cover flag: best-effort via output scan; we don't enforce a you-get flag here.
    _ = cover
    cmd.append(url)
    return cmd


def _build_ytdlp_cmd(url: str, *, out_dir: Path, playlist: bool, subtitles: bool, cover: bool, have_ffmpeg: bool) -> list[str]:
    cmd = _yt_dlp_cmd() + ["-P", str(out_dir)]
    cmd += ["--no-warnings"]
    cmd += ["--newline"]
    cmd += ["--no-color"]
    if playlist:
        # If downloading a playlist, don't fail the entire job on a single broken entry.
        cmd += ["--ignore-errors"]

    if have_ffmpeg:
        # Best quality (video+audio) and merge to mp4.
        cmd += ["-f", "bv*+ba/b"]
        cmd += ["--merge-output-format", "mp4"]
    else:
        # Without ffmpeg, prefer a single-file format that already contains audio.
        cmd += ["-f", "best[ext=mp4][acodec!=none]/best[acodec!=none]/best"]

    if playlist:
        cmd += ["--yes-playlist"]
        cmd += ["-o", "%(playlist_title).80s/%(playlist_index)03d - %(title).200s [%(id)s].%(ext)s"]
    else:
        cmd += ["--no-playlist"]
        cmd += ["-o", "%(title).200s [%(id)s].%(ext)s"]

    if subtitles:
        cmd += ["--write-subs", "--write-auto-subs", "--sub-langs", "all"]
        if have_ffmpeg:
            cmd += ["--convert-subs", "srt"]

    if cover:
        cmd += ["--write-thumbnail"]
        if have_ffmpeg:
            cmd += ["--convert-thumbnails", "jpg"]

    cmd.append(url)
    return cmd


def _apply_ytdlp_cookies(cmd: list[str], *, cookies: dict) -> list[str]:
    file_path = (cookies or {}).get("file_path") or ""
    from_browser = bool((cookies or {}).get("from_browser"))
    browser = ((cookies or {}).get("browser") or "chrome").strip().lower()
    profile = ((cookies or {}).get("profile") or "").strip()

    def insert_opts(args: list[str]) -> list[str]:
        if not args:
            return cmd
        if cmd and isinstance(cmd[-1], str) and cmd[-1].startswith(("http://", "https://")):
            return cmd[:-1] + args + [cmd[-1]]
        return cmd + args

    if file_path:
        return insert_opts(["--cookies", file_path])
    if from_browser:
        browser_arg = browser
        if profile:
            browser_arg = f"{browser}:{profile}"
        return insert_opts(["--cookies-from-browser", browser_arg])
    return cmd


def _zip_outputs(*, root: Path, files: list[Path], zip_path: Path, include_cover: bool, include_subtitles: bool) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            kind = classify_kind(p)
            if not kind:
                continue
            if kind == "subtitle" and not include_subtitles:
                continue
            if kind == "cover" and not include_cover:
                continue
            arc = safe_rel_name(root, p)
            if not arc:
                continue
            zf.write(p, arcname=arc)


def run_task(task_id: str) -> int:
    app = create_app()
    with app.app_context():
        paths = get_video_job_paths(task_id)
        task = read_json(paths.task_json)
        url = task.get("url") or ""
        opts = task.get("options") or {}
        playlist = bool(opts.get("playlist"))
        subtitles = bool(opts.get("subtitles"))
        cover = bool(opts.get("cover"))
        have_ffmpeg = bool(app.config.get("VIDEO_HAVE_FFMPEG"))
        cookies = task.get("cookies") or {}

        if not shutil.which(sys.executable):
            raise VideoJobError("Python 不可用。")

        out_dir = create_tmp_dir(task_id)
        append_log(paths.task_log, f"[start] task={task_id}")
        append_log(paths.task_log, f"[options] playlist={playlist} subtitles={subtitles} cover={cover}")

        task["status"] = "running"
        task["started_at"] = int(time.time())
        atomic_write_json(paths.task_json, task)

        use_ytdlp = _is_youtube(url) and bool(app.config.get("VIDEO_HAVE_YTDLP"))
        if use_ytdlp:
            cmd = _build_ytdlp_cmd(url, out_dir=out_dir, playlist=playlist, subtitles=subtitles, cover=cover, have_ffmpeg=have_ffmpeg)
            cmd = _apply_ytdlp_cookies(cmd, cookies=cookies)
            append_log(paths.task_log, "[engine] yt-dlp (auto for YouTube)")
        else:
            cmd = _build_download_cmd(url, out_dir=out_dir, playlist=playlist, subtitles=subtitles, cover=cover)
            append_log(paths.task_log, "[engine] you-get")
        append_log(paths.task_log, f"[cmd] {' '.join(cmd)}")

        recent: list[str] = []
        recent_fallback: list[str] = []
        proc = subprocess.Popen(
            cmd,
            cwd=str(out_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        task["you_get_pid"] = proc.pid
        atomic_write_json(paths.task_json, task)

        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                s = line.rstrip("\n")
                append_log(paths.task_log, s)
                recent.append(s)
                if len(recent) > 80:
                    recent = recent[-80:]
        except Exception as exc:
            append_log(paths.task_log, f"[warn] log capture failed: {exc}")

        code = proc.wait()
        append_log(paths.task_log, f"[exit] code={code}")
        if code != 0 and use_ytdlp:
            joined = "\n".join(recent).lower()
            if "sign in to confirm you" in joined or "not a bot" in joined:
                raise VideoJobError("YouTube 要求验证“你不是机器人”。请勾选“从浏览器读取 Cookies”或上传 cookies.txt 后重试。")

        if code != 0 and not use_ytdlp and bool(app.config.get("VIDEO_HAVE_YTDLP")):
            # Fallback for sites where you-get is outdated (notably YouTube).
            append_log(paths.task_log, "[fallback] you-get failed; retry with yt-dlp")
            cmd2 = _build_ytdlp_cmd(url, out_dir=out_dir, playlist=playlist, subtitles=subtitles, cover=cover, have_ffmpeg=have_ffmpeg)
            cmd2 = _apply_ytdlp_cookies(cmd2, cookies=cookies)
            append_log(paths.task_log, f"[cmd] {' '.join(cmd2)}")
            proc2 = subprocess.Popen(
                cmd2,
                cwd=str(out_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )
            task["yt_dlp_pid"] = proc2.pid
            atomic_write_json(paths.task_json, task)
            try:
                assert proc2.stdout is not None
                for line in proc2.stdout:
                    s = line.rstrip("\n")
                    append_log(paths.task_log, s)
                    recent_fallback.append(s)
                    if len(recent_fallback) > 120:
                        recent_fallback = recent_fallback[-120:]
            except Exception as exc:
                append_log(paths.task_log, f"[warn] log capture failed: {exc}")
            code = proc2.wait()
            append_log(paths.task_log, f"[exit] yt-dlp code={code}")

        if code != 0:
            if _is_youtube(url) and not bool(app.config.get("VIDEO_HAVE_YTDLP")):
                raise VideoJobError("下载失败：you-get 对 YouTube 可能已失效；建议安装 yt-dlp 后重试。")
            raise VideoJobError("下载失败：下载引擎返回非 0。")

        files = iter_output_files(out_dir)
        if not files:
            diag = "\n".join((recent + recent_fallback)[-160:]).lower()
            if "downloading 0 items" in diag or "playlist" in diag and "0 items" in diag:
                raise VideoJobError("该链接被识别为合集/剧集页面，但解析到 0 个可下载条目；请换成具体分集/视频链接，或尝试勾选“下载合集/播放列表”。")
            raise VideoJobError("未找到下载产物：可能站点解析失败、需要 Cookies/地区限制，或下载到的格式未被识别。")

        task["status"] = "zipping"
        atomic_write_json(paths.task_json, task)

        zip_path = out_dir / f"bundle_{task_id[:10]}.zip"
        _zip_outputs(root=out_dir, files=files, zip_path=zip_path, include_cover=cover, include_subtitles=subtitles)

        results_files: list[dict[str, str]] = []
        for p in files:
            kind = classify_kind(p)
            if not kind:
                continue
            if kind == "subtitle" and not subtitles:
                continue
            if kind == "cover" and not cover:
                continue

            rel_name = safe_rel_name(out_dir, p)
            download_name = rel_name.replace("/", "_")
            job_id = save_output_file(p, download_name=download_name, mimetype=guess_mimetype(download_name))
            results_files.append(
                {
                    "job_id": job_id,
                    "name": rel_name,
                    "kind": kind,
                    "mimetype": guess_mimetype(download_name),
                }
            )

        zip_job_id = save_output_file(zip_path, download_name=f"video_bundle_{task_id[:10]}.zip", mimetype="application/zip")

        task["status"] = "done"
        task["finished_at"] = int(time.time())
        task["results"] = {"files": results_files, "zip_job_id": zip_job_id}
        task["error"] = None
        atomic_write_json(paths.task_json, task)
        append_log(paths.task_log, "[done]")

        # Best-effort cleanup of uploaded cookies file.
        try:
            cookie_path = (cookies or {}).get("file_path") or ""
            if cookie_path:
                Path(cookie_path).unlink(missing_ok=True)
        except Exception:
            pass

        try:
            shutil.rmtree(out_dir, ignore_errors=True)
        except Exception:
            pass

        return 0


def fail_task(task_id: str, msg: str) -> int:
    app = create_app()
    with app.app_context():
        try:
            paths = get_video_job_paths(task_id)
            append_log(paths.task_log, f"[error] {msg}")
            task = read_json(paths.task_json)
            task["status"] = "failed"
            task["error"] = msg
            task["finished_at"] = int(time.time())
            atomic_write_json(paths.task_json, task)
        except Exception:
            pass
    return 1


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return 2
    task_id = (argv[1] or "").strip().lower()
    try:
        return run_task(task_id)
    except Exception as exc:
        return fail_task(task_id, str(exc))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
