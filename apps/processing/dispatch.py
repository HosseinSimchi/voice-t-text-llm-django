"""Enqueue Celery tasks only after the surrounding DB transaction commits."""

from __future__ import annotations

import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def _send(task_name: str, args: list, countdown: float | None = None) -> None:
    from config.celery import app

    try:
        app.send_task(task_name, args=args, countdown=countdown) if not app.conf.task_always_eager \
            else app.tasks[task_name].apply_async(args=args, countdown=countdown)
    except Exception:  # broker down: state is in the DB, recovery will re-enqueue
        logger.exception("Could not enqueue %s%s; the recovery task will retry it", task_name, args)


def enqueue(task_name: str, *args, countdown: float | None = None) -> None:
    transaction.on_commit(lambda: _send(task_name, [str(a) for a in args], countdown))


def enqueue_job(job_id, countdown: float | None = None) -> None:
    enqueue("processing.run_job", job_id, countdown=countdown)


def enqueue_file(file_id, countdown: float | None = None) -> None:
    enqueue("processing.process_file", file_id, countdown=countdown)


def enqueue_email(job_id, countdown: float | None = None) -> None:
    enqueue("notifications.send_job_email", job_id, countdown=countdown)
