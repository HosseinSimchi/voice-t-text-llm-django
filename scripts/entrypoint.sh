#!/bin/sh
# Container entrypoint: web | worker | beat | migrate | manage <args>
set -eu

case "${1:-web}" in
  web)
    python manage.py validate_config
    exec gunicorn config.wsgi:application \
      --bind 0.0.0.0:8000 \
      --workers "${GUNICORN_WORKERS:-2}" \
      --timeout "${GUNICORN_TIMEOUT:-300}" \
      --worker-tmp-dir /dev/shm \
      --limit-request-line 8190 \
      --access-logfile - --error-logfile -
    ;;
  worker)
    # Concurrency 1 by default: Whisper and the LLM are CPU/RAM heavy.
    exec celery -A config worker --loglevel "${LOG_LEVEL:-INFO}" \
      --concurrency "${CELERY_CONCURRENCY:-1}" --max-tasks-per-child "${CELERY_MAX_TASKS_PER_CHILD:-50}" \
      -Q celery
    ;;
  beat)
    exec celery -A config beat --loglevel "${LOG_LEVEL:-INFO}" \
      --schedule /app/media/.celerybeat-schedule
    ;;
  migrate)
    # One-off: apply database migrations (docker compose runs this before web/worker/beat start).
    python manage.py validate_config
    exec python manage.py migrate --noinput
    ;;
  manage)
    shift
    exec python manage.py "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
