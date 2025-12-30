FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Mirrors (override at build time if needed)
# Example:
#   docker build --build-arg APT_MIRROR_URL=https://mirrors.aliyun.com \
#                --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple \
#                -t watermark-studio .
ARG APT_MIRROR_URL=https://mirrors.tuna.tsinghua.edu.cn
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

# System deps:
# - fonts-noto-cjk: make Chinese text watermark visible in container
# - libglib2.0-0/libgl1: common runtime deps for opencv wheels (headless)
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i -E "s|https?://deb\\.debian\\.org/debian|${APT_MIRROR_URL}/debian|g; s|https?://security\\.debian\\.org/debian-security|${APT_MIRROR_URL}/debian-security|g" /etc/apt/sources.list.d/debian.sources; \
    fi; \
    if [ -f /etc/apt/sources.list ]; then \
      sed -i -E "s|https?://deb\\.debian\\.org/debian|${APT_MIRROR_URL}/debian|g; s|https?://security\\.debian\\.org/debian-security|${APT_MIRROR_URL}/debian-security|g" /etc/apt/sources.list; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
    fonts-noto-cjk \
    libglib2.0-0 \
    libgl1 \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" --trusted-host "$PIP_TRUSTED_HOST" -r /app/requirements.txt

COPY . /app

RUN useradd -m -u 10001 appuser \
  && mkdir -p /app/instance/outputs \
  && chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

CMD ["gunicorn", "-b", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "120", "app:app"]
