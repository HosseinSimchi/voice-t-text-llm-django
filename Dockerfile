# syntax=docker/dockerfile:1.7
# One image for web, worker, beat and one-off commands (migrate). CPU-only by default.
# Build:  docker build -t audio-intelligence:1.0.0 .
FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.title="Persian Audio Intelligence Platform" \
      org.opencontainers.image.description="Django + Celery app: Persian speech-to-text, PDFs, local-LLM extraction, e-mail"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/app/models/huggingface \
    DJANGO_SETTINGS_MODULE=config.settings.prod

# ffmpeg: audio probing and normalisation.
# libarchive-tools (bsdtar): free RAR3/RAR5 extraction backend for `rarfile` (extraction only).
# curl: health checks.
# Packages are fetched over HTTPS because some networks block plain-HTTP mirrors.
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
 && apt-get -o Acquire::Retries=5 update \
 && apt-get -o Acquire::Retries=5 install -y --no-install-recommends ffmpeg libarchive-tools curl \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home /app --shell /usr/sbin/nologin app

WORKDIR /app
COPY requirements.txt .
# requirements.txt is fully pinned (generated with `uv pip compile requirements.in`).
# Retried because package downloads occasionally fail on unreliable networks.
RUN for i in 1 2 3 4 5; do \
      pip install --retries 10 --timeout 60 -r requirements.txt && exit 0; \
      echo "pip install failed (attempt $i), retrying in 10 s" >&2; sleep 10; \
    done; exit 1

COPY --chown=app:app . .
# Shell scripts must have Unix line endings (a CRLF shebang makes the container fail to start).
RUN sed -i 's/\r$//' scripts/*.sh \
 && chmod +x scripts/*.sh \
 && mkdir -p /app/media /app/logs /app/models /app/staticfiles \
 && DJANGO_SECRET_KEY=build-only-not-secret-0123456789abcdefghijklmnopqrstuvwxyz0123 \
    VALIDATE_APP_CONFIG_ON_STARTUP=false LOG_TO_FILE=false \
    python manage.py collectstatic --noinput \
 && chown -R app:app /app/media /app/logs /app/models /app/staticfiles \
 && chmod 750 /app/media /app/logs

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["web"]
