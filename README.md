# Watermark Studio

本地运行的 Flask Web 小工具：PDF/图片水印的去除与添加，支持网页端预览确认后再下载（默认不上传到任何第三方服务）。

## 功能

- PDF 去水印：清理常见注释水印（`/Watermark`/`/Stamp`）、`Artifact Watermark` 标记内容；可选增强模式与“尝试去除图片水印”，并给出统计与文本相似度抽样对比
- PDF 加水印：支持文字水印（单点/平铺，可调字号/颜色/透明度/旋转/位置）与图片水印（单点/平铺、缩放、透明度、旋转）
- 图片加水印：文字水印（单点/平铺，可调字号/颜色/透明度/旋转/位置），并提供原图/结果预览
- 图片去水印：支持画布框选一个或多个区域精准去除；不框选时自动检测 + OpenCV 修复（可调强度/算法/半径/遮罩扩展）
- 图片压缩：支持常用比例裁剪/自定义输出像素，并可设置目标大小（默认不超过）输出尽量清晰的结果（支持预览后下载）

## 本地运行

方式 A：手动安装依赖并启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

方式 B：一键脚本（会尝试使用 `.venv`，否则回退到系统 `python3`）

```bash
./run_local.sh
```

访问：`http://127.0.0.1:5000`

调试模式（可选）：

```bash
flask --app app run --debug
```

## Docker 运行

构建并运行：

```bash
docker build -t watermark-studio .
docker run --rm -p 5000:5000 -v "$(pwd)/instance:/app/instance" watermark-studio
```

或使用 Compose：

```bash
docker compose up --build
```

访问：`http://127.0.0.1:5000`

## Render 部署（公网访问）

1) 将本项目推到 GitHub
2) Render 控制台：New → **Blueprint** → 选择仓库（会识别 `render.yaml`）
3) 点击 Deploy，等待构建完成后即可通过 Render 提供的 `https://...` 域名访问

本项目在 Render 上的启动命令为：

```bash
gunicorn -w 2 -b 0.0.0.0:$PORT app:app
```

## 页面与接口

页面入口：

- `/`：首页
- `/pdf/remove`：PDF 去水印（预览 + 下载）
- `/pdf/add-watermark`：PDF 加水印（预览 + 下载）
- `/image/add-watermark`：图片加水印（预览 + 下载）
- `/image/remove-watermark`：图片去水印（预览 + 下载）
- `/image/compress`：图片压缩（裁剪 + 目标大小，预览 + 下载）

文件预览/下载：

- `/files/<job_id>`：预览
- `/files/<job_id>?download=1`：下载

同一路由在请求头携带 `Accept: application/json` 时会返回 JSON（前端表单就是通过该方式提交的），便于脚本化调用。

## 配置

- 上传大小限制：默认 50MB（`watermark_studio/__init__.py` 里的 `MAX_CONTENT_LENGTH`）
- 应用名称：`APP_NAME`（会显示在页面标题/导航栏）
- 图片水印字体：可通过环境变量 `WATERMARK_FONT_PATH` 指定字体文件路径（用于图片文字水印在容器/服务器中更好显示中文）
  - Docker/Compose 示例：`-e WATERMARK_FONT_PATH=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`

## 输出文件存储

处理结果会保存到 `instance/outputs/`（文件名为 `job_id`，并配套一个 `job_id.meta` 存储 `mimetype` 与下载文件名）。

- 清理历史结果：直接删除 `instance/outputs/` 下的文件即可
- 注意：当前版本不会自动清理历史输出，长期使用建议定期清理

## 目录结构

- `app.py`：应用入口（创建 Flask app）
- `watermark_studio/`：核心代码
  - `blueprints/`：路由与页面
  - `services/`：PDF/图片处理与输出存储
  - `utils/`：上传校验等通用工具
- `templates/`：Jinja2 模板
- `static/`：CSS/JS 静态资源

## 免责声明

去水印属于启发式处理，不同文件结构差异很大：可能去不干净，也可能误删内容。请务必使用页面预览对比并保留原文件备份。

## 第三方库说明

- 图片压缩页面的裁剪交互使用 Cropper.js（已 vendored 到 `static/vendor/cropperjs/`）。
