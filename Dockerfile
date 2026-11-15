# syntax=docker/dockerfile:1.7
# Production image for web, worker and beat (CPU-only by default).
FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/app/models/huggingface \
    DJANGO_SETTINGS_MODULE=config.settings.prod

# ffmpeg: audio normalisation/probing.  7zip: RAR extraction backend for rarfile
# (RAR decompression code is under the unRAR licence: extraction only, no RAR creation).
# Fetch Debian packages over HTTPS (some networks block plain-HTTP mirrors).
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
 && apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg 7zip libarchive-tools curl \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --home /app --shell /usr/sbin/nologin app

WORKDIR /app
COPY requirements.txt .
# requirements.txt is fully pinned (generated with `uv pip compile requirements.in`).
RUN pip install --retries 10 --timeout 60 -r requirements.txt

COPY --chown=app:app . .
RUN mkdir -p /app/media /app/logs /app/models /app/staticfiles \
 && DJANGO_SECRET_KEY=build-only-not-secret-0123456789abcdefghijklmnopqrstuvwxyz0123 \
    VALIDATE_APP_CONFIG_ON_STARTUP=false LOG_TO_FILE=false \
    python manage.py collectstatic --noinput \
 && chown -R app:app /app/media /app/logs /app/models /app/staticfiles \
 && chmod 750 /app/media /app/logs \
 && chmod +x scripts/*.sh

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["web"]
