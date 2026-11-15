"""Celery application. Task state of record is the database, not Celery."""

import os

from celery import Celery
from celery.signals import worker_ready

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("audio_intelligence")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@worker_ready.connect
def _log_llm_health(**kwargs):
    """Make an unavailable LLM obvious when the worker starts instead of when the first job fails."""
    import logging

    log = logging.getLogger("apps.worker")
    try:
        from apps.core.config import get_config
        from apps.information_extraction.providers.registry import build_provider

        cfg = get_config()
        ok, message = build_provider(cfg.llm).healthcheck()
        (log.info if ok else log.warning)("LLM preflight: %s", message)
        from django.conf import settings

        if not getattr(settings, "EMAIL_REAL_DELIVERY", False):
            log.warning("E-mail backend is %s: result e-mails are NOT delivered to recipients. "
                        "Configure SMTP (EMAIL_* variables) to send real e-mail.", settings.EMAIL_BACKEND)
    except Exception:  # noqa: BLE001 - diagnostics must never stop the worker
        log.exception("LLM preflight could not run")
