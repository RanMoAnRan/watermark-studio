from __future__ import annotations

import io
import json
import re
import textwrap
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

from PIL import Image, ImageDraw, ImageFont
from PIL import ImageOps


class InvalidWebAppOptionsError(ValueError):
    pass


@dataclass(frozen=True)
class WebAppPackageOptions:
    target_url: str
    app_name: str
    theme_color: str
    app_id: str
    icon_bytes: bytes | None = None


_APP_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def normalize_target_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raise InvalidWebAppOptionsError("请输入网站地址。")

    if "://" not in raw:
        raw = "https://" + raw

    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise InvalidWebAppOptionsError("仅支持 http/https 网站。")
    if not parsed.netloc:
        raise InvalidWebAppOptionsError("网站地址无效，请包含域名，例如：https://example.com")

    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
    )
    return urlunparse(normalized)


def normalize_theme_color(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return "#111827"
    if not _HEX_COLOR_RE.match(raw):
        raise InvalidWebAppOptionsError("主题色格式错误，请使用 #RRGGBB。")
    return raw.lower()


def suggest_app_name(target_url: str) -> str:
    host = (urlparse(target_url).hostname or "").strip()
    host = host[4:] if host.startswith("www.") else host
    if not host:
        return "WebApp"
    return host.split(".")[0] or "WebApp"


def normalize_app_name(raw: str, *, target_url: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raw = suggest_app_name(target_url)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:40] if len(raw) > 40 else raw


def suggest_app_id(target_url: str) -> str:
    host = (urlparse(target_url).hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    parts = [p for p in host.split(".") if p]
    if len(parts) < 2:
        parts = ["example", "app"]
    parts = list(reversed(parts))

    def _seg(seg: str) -> str:
        seg = re.sub(r"[^a-z0-9_]", "_", seg)
        seg = re.sub(r"_+", "_", seg).strip("_")
        if not seg:
            seg = "app"
        if not seg[0].isalpha():
            seg = "app_" + seg
        return seg

    normalized = [_seg(p) for p in parts]
    if len(normalized) < 2:
        normalized = ["com"] + normalized
    return ".".join(normalized[:4])


def normalize_app_id(raw: str, *, target_url: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raw = suggest_app_id(target_url)
    if not _APP_ID_RE.match(raw):
        raise InvalidWebAppOptionsError("App ID（包名）格式错误，例如：com.example.myapp")
    return raw


def safe_download_stem(app_name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", (app_name or "").strip()) or "webapp"
    stem = re.sub(r"_+", "_", stem).strip("_")
    return stem[:60] if len(stem) > 60 else stem


def _zip_mtime() -> tuple[int, int, int, int, int, int]:
    dt = datetime.now(timezone.utc).astimezone()
    return (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)


def _zip_write_text(zf: zipfile.ZipFile, path: str, text: str) -> None:
    info = zipfile.ZipInfo(filename=path, date_time=_zip_mtime())
    info.compress_type = zipfile.ZIP_DEFLATED
    zf.writestr(info, text.encode("utf-8"))


def _zip_write_bytes(zf: zipfile.ZipFile, path: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(filename=path, date_time=_zip_mtime())
    info.compress_type = zipfile.ZIP_DEFLATED
    zf.writestr(info, payload)


def _make_icon_png(app_name: str, *, size: int, theme_color: str) -> bytes:
    img = Image.new("RGBA", (size, size), theme_color)
    draw = ImageDraw.Draw(img)

    text = (app_name or "A").strip()[:2].upper()
    if not text:
        text = "A"

    font = None
    for font_name in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(font_name, int(size * 0.42))
            break
        except Exception:
            font = None
    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size - text_w) / 2
    y = (size - text_h) / 2
    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _make_icon_from_upload(icon_bytes: bytes, *, size: int, theme_color: str) -> bytes:
    try:
        src = Image.open(io.BytesIO(icon_bytes))
        src = src.convert("RGBA")
    except Exception as exc:
        raise InvalidWebAppOptionsError(f"图标图片无法解析：{exc}") from exc

    canvas = Image.new("RGBA", (size, size), theme_color)
    fitted = ImageOps.contain(src, (size, size))
    x = (size - fitted.width) // 2
    y = (size - fitted.height) // 2
    canvas.alpha_composite(fitted, (x, y))

    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _icon_png(options: WebAppPackageOptions, *, size: int) -> bytes:
    if options.icon_bytes:
        return _make_icon_from_upload(options.icon_bytes, size=size, theme_color=options.theme_color)
    return _make_icon_png(options.app_name, size=size, theme_color=options.theme_color)


def build_pwa_zip(options: WebAppPackageOptions) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        _zip_write_text(
            zf,
            "README.md",
            textwrap.dedent(
                f"""\
                # {options.app_name}（PWA 包）

                这是一个“把网站打包成可安装 PWA”的静态项目。

                - 目标网站：{options.target_url}
                - 注意：如果目标站点设置了 `X-Frame-Options` / `CSP frame-ancestors`，可能无法在 iframe 内嵌显示；此时会提示你改为“直接打开网站”。

                ## 本地运行

                在本目录启动静态服务器（任选其一）：

                - Python：`python -m http.server 8000`
                - Node：`npx serve .`

                然后访问：`http://localhost:8000`

                ## 安装

                在 Chrome / Edge / Android Chrome 中打开后，浏览器菜单里选择“安装应用”。
                """
            ),
        )

        _zip_write_text(
            zf,
            "index.html",
            textwrap.dedent(
                f"""\
                <!doctype html>
                <html lang="zh-CN">
                  <head>
                    <meta charset="utf-8" />
                    <meta name="viewport" content="width=device-width, initial-scale=1" />
                    <meta name="theme-color" content="{options.theme_color}" />
                    <title>{options.app_name}</title>
                    <link rel="manifest" href="./manifest.webmanifest" />
                    <link rel="icon" href="./icons/favicon-192.png" />
                    <link rel="apple-touch-icon" href="./icons/apple-touch-icon.png" />
                    <link rel="stylesheet" href="./app.css" />
                  </head>
                  <body>
                    <div class="bar">
                      <div class="title">{options.app_name}</div>
                      <div class="actions">
                        <a id="openExternal" class="btn" href="#" rel="noreferrer">在浏览器打开</a>
                      </div>
                    </div>
                    <div class="body">
                      <iframe id="frame" title="webapp" referrerpolicy="no-referrer"></iframe>
                      <div id="fallback" class="fallback" style="display:none;">
                        <div class="hint">
                          该网站可能禁止被内嵌显示（X-Frame-Options / CSP）。你仍可以在本窗口直接打开它。
                        </div>
                        <button id="openHere" class="btn primary">直接打开网站</button>
                      </div>
                    </div>
                    <script src="./config.js"></script>
                    <script src="./app.js"></script>
                  </body>
                </html>
                """
            ),
        )

        _zip_write_text(
            zf,
            "config.js",
            f'window.__WEBAPP_TARGET_URL__ = {json.dumps(options.target_url, ensure_ascii=False)};\n',
        )

        _zip_write_text(
            zf,
            "app.css",
            textwrap.dedent(
                f"""\
                :root {{
                  --bg: #0b1220;
                  --panel: #0f172a;
                  --text: #e5e7eb;
                  --muted: #94a3b8;
                  --brand: {options.theme_color};
                }}
                * {{ box-sizing: border-box; }}
                html, body {{ height: 100%; margin: 0; background: var(--bg); color: var(--text); font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; }}
                .bar {{ height: 52px; display: flex; align-items: center; justify-content: space-between; padding: 0 12px; background: var(--panel); border-bottom: 1px solid rgba(148,163,184,.2); }}
                .title {{ font-weight: 700; }}
                .body {{ height: calc(100% - 52px); position: relative; }}
                #frame {{ width: 100%; height: 100%; border: 0; background: #fff; }}
                .btn {{ display: inline-flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 10px; text-decoration: none; color: var(--text); border: 1px solid rgba(148,163,184,.25); background: rgba(148,163,184,.08); }}
                .btn.primary {{ background: var(--brand); border-color: var(--brand); color: #fff; }}
                .fallback {{ position: absolute; inset: 0; display: grid; place-items: center; background: rgba(2,6,23,.85); padding: 16px; }}
                .hint {{ max-width: 520px; color: var(--muted); line-height: 1.5; margin-bottom: 12px; }}
                """
            ),
        )

        _zip_write_text(
            zf,
            "app.js",
            textwrap.dedent(
                """\
                (() => {
                  const targetUrl = window.__WEBAPP_TARGET_URL__ || "";
                  const frame = document.getElementById("frame");
                  const openExternal = document.getElementById("openExternal");
                  const fallback = document.getElementById("fallback");
                  const openHere = document.getElementById("openHere");

                  if (!targetUrl) {
                    fallback.style.display = "";
                    openHere.addEventListener("click", () => alert("缺少目标网站 URL。"));
                    return;
                  }

                  openExternal.href = targetUrl;
                  openHere.addEventListener("click", () => {
                    window.location.href = targetUrl;
                  });

                  let timer = setTimeout(() => {
                    // 若站点加载过慢或禁止内嵌，这里给出降级入口（仍可直接打开网站）。
                    fallback.style.display = "";
                  }, 1800);

                  frame.addEventListener("load", () => {
                    if (timer) clearTimeout(timer);
                    timer = null;
                    fallback.style.display = "none";
                  });

                  frame.src = targetUrl;

                  if ("serviceWorker" in navigator) {
                    window.addEventListener("load", () => {
                      navigator.serviceWorker.register("./sw.js").catch(() => {});
                    });
                  }
                })();
                """
            ),
        )

        manifest = {
            "name": options.app_name,
            "short_name": options.app_name[:12],
            "start_url": "./index.html",
            "scope": "./",
            "display": "standalone",
            "background_color": "#0b1220",
            "theme_color": options.theme_color,
            "icons": [
                {"src": "./icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "./icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
                {"src": "./icons/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
            ],
        }
        _zip_write_text(zf, "manifest.webmanifest", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

        _zip_write_text(
            zf,
            "sw.js",
            textwrap.dedent(
                """\
                const CACHE = "webapp-shell-v1";
                const ASSETS = ["./", "./index.html", "./app.css", "./app.js", "./config.js", "./manifest.webmanifest"];

                self.addEventListener("install", (event) => {
                  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ASSETS)));
                  self.skipWaiting();
                });

                self.addEventListener("activate", (event) => {
                  event.waitUntil(self.clients.claim());
                });

                self.addEventListener("fetch", (event) => {
                  const req = event.request;
                  const url = new URL(req.url);
                  if (url.origin !== self.location.origin) return;
                  event.respondWith(caches.match(req).then((hit) => hit || fetch(req)));
                });
                """
            ),
        )

        _zip_write_bytes(zf, "icons/icon-192.png", _icon_png(options, size=192))
        _zip_write_bytes(zf, "icons/icon-512.png", _icon_png(options, size=512))
        _zip_write_bytes(zf, "icons/favicon-192.png", _icon_png(options, size=192))
        _zip_write_bytes(zf, "icons/apple-touch-icon.png", _icon_png(options, size=180))
        _zip_write_bytes(zf, "icons/icon-512-maskable.png", _icon_png(options, size=512))

    return buf.getvalue()


def build_capacitor_zip(options: WebAppPackageOptions, *, focus: str) -> bytes:
    if focus not in {"android", "ios", "all"}:
        focus = "all"

    cleartext = urlparse(options.target_url).scheme == "http"
    allow_nav = []
    host = urlparse(options.target_url).hostname
    if host:
        allow_nav = [host, f"*.{host}"]

    capacitor_config = {
        "appId": options.app_id,
        "appName": options.app_name,
        "webDir": "www",
        "bundledWebRuntime": False,
        "server": {
            "url": options.target_url,
            "cleartext": cleartext,
        },
        "allowNavigation": allow_nav,
    }

    package_json = {
        "name": safe_download_stem(options.app_name).lower(),
        "private": True,
        "version": "0.0.0",
        "dependencies": {"@capacitor/core": "^6.0.0"},
        "devDependencies": {
            "@capacitor/assets": "^3.0.0",
            "@capacitor/cli": "^6.0.0",
            "@capacitor/android": "^6.0.0",
            "@capacitor/ios": "^6.0.0",
        },
    }

    readme_steps = {
        "android": textwrap.dedent(
            """\
            ## 安卓打包

            1) 安装依赖：`npm install`
            2) 生成安卓工程：`npx cap add android`
            3) 生成图标/启动图（可选）：`npx capacitor-assets generate`
            3) 打开 Android Studio：`npx cap open android`
            4) 在 Android Studio 里 Build / Generate APK/AAB
            """
        ),
        "ios": textwrap.dedent(
            """\
            ## iOS 打包

            1) 安装依赖：`npm install`
            2) 生成 iOS 工程：`npx cap add ios`
            3) 生成图标/启动图（可选）：`npx capacitor-assets generate`
            3) 打开 Xcode：`npx cap open ios`
            4) 在 Xcode 里 Archive / Export
            """
        ),
        "all": textwrap.dedent(
            """\
            ## 安卓 / iOS 打包

            - 安装依赖：`npm install`
            - 生成安卓工程：`npx cap add android`
            - 生成 iOS 工程：`npx cap add ios`
            - 生成图标/启动图（可选）：`npx capacitor-assets generate`
            - 打开 Android Studio：`npx cap open android`
            - 打开 Xcode：`npx cap open ios`
            """
        ),
    }[focus]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        _zip_write_text(
            zf,
            "README.md",
            textwrap.dedent(
                f"""\
                # {options.app_name}（Capacitor 工程）

                这是一个“把网站打包成原生 App（安卓/iOS）”的工程模板，使用 Capacitor 的 `server.url` 直接加载你输入的网站。

                - 目标网站：{options.target_url}
                - App ID（包名）：{options.app_id}

                ## 准备环境

                - Node.js 18+ / npm
                - Android：Android Studio（含 SDK）
                - iOS：macOS + Xcode

                {readme_steps.strip()}

                ## 重要说明

                - 该方案本质是 WebView 打开远程站点，离线能力取决于目标站点。
                - 如果是 http 网站：Android 需要允许明文流量；iOS 可能需要额外配置（App Transport Security）。
                """
            )
            + "\n",
        )

        _zip_write_text(zf, "package.json", json.dumps(package_json, ensure_ascii=False, indent=2) + "\n")
        _zip_write_text(zf, "capacitor.config.json", json.dumps(capacitor_config, ensure_ascii=False, indent=2) + "\n")
        _zip_write_text(zf, ".gitignore", "node_modules/\nandroid/\nios/\n.DS_Store\n")
        _zip_write_text(
            zf,
            "www/index.html",
            textwrap.dedent(
                f"""\
                <!doctype html>
                <html lang="zh-CN">
                  <head>
                    <meta charset="utf-8" />
                    <meta name="viewport" content="width=device-width, initial-scale=1" />
                    <title>{options.app_name}</title>
                  </head>
                  <body>
                    <h3>{options.app_name}</h3>
                    <p>该工程使用 Capacitor 的 <code>server.url</code> 加载远程站点：</p>
                    <p><a href="{options.target_url}" rel="noreferrer">{options.target_url}</a></p>
                    <p>如果你在浏览器里看到这里，说明你尚未生成平台工程（android/ios）。</p>
                  </body>
                </html>
                """
            ),
        )

        _zip_write_bytes(zf, "www/icon-512.png", _icon_png(options, size=512))
        _zip_write_bytes(zf, "resources/icon.png", _icon_png(options, size=1024))

    return buf.getvalue()
