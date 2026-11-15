"""Recovery of interrupted work and retention-aware cleanup (run by Celery Beat)."""

from __future__ import annotations

import logging
import time
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.core.config import get_config
from apps.uploads import storage

from . import dispatch
from .models import TERMINAL_FILE_STATUSES, TERMINAL_JOB_STATUSES, EmailStatus, Job, JobStage, JobStatus

logger = logging.getLogger(__name__)


def _lease_free(now):
    return Q(lease_until__isnull=True) | Q(lease_until__lt=now)


def _due(obj, now, stale_before) -> bool:
    """Work is due when its scheduled retry time passed, or it has been idle too long."""
    if obj.next_attempt_at is not None:
        return obj.next_attempt_at <= now
    return obj.updated_at <= stale_before


def recover_jobs() -> dict[str, int]:
    """Re-enqueue eligible stages of non-terminal jobs whose worker vanished.

    Safe to run any number of times: every task is idempotent and lease-protected.
    """
    cfg = get_config()
    now = timezone.now()
    stale_before = now - timedelta(seconds=int(cfg.app["processing"]["stale_after_seconds"]))
    max_age = timedelta(seconds=int(cfg.storage["max_retention_seconds"]))
    stats = {"jobs": 0, "files": 0, "emails": 0, "expired": 0, "finalized": 0}

    for job in Job.objects.exclude(status__in=TERMINAL_JOB_STATUSES).filter(_lease_free(now)):
        if now - job.uploaded_at > max_age:
            _expire(job)
            stats["expired"] += 1
            continue
        if job.stage == JobStage.ARCHIVE_EXTRACTION:
            if _due(job, now, stale_before):
                Job.objects.filter(pk=job.pk).update(updated_at=now)
                dispatch.enqueue_job(job.id)
                stats["jobs"] += 1
        elif job.stage == JobStage.FILE_PROCESSING:
            active = job.files.exclude(status__in=TERMINAL_FILE_STATUSES)
            if not active.exists():
                from .pipeline import finalize_job

                finalize_job(job.id)
                stats["finalized"] += 1
                continue
            for f in active.filter(_lease_free(now)):
                if _due(f, now, stale_before):
                    type(f).objects.filter(pk=f.pk).update(updated_at=now)
                    dispatch.enqueue_file(f.id)
                    stats["files"] += 1
        elif job.stage == JobStage.EMAIL_DELIVERY:
            if job.email_status in (EmailStatus.PENDING, EmailStatus.RETRYING, EmailStatus.SENDING) \
                    and _due(job, now, stale_before):
                Job.objects.filter(pk=job.pk).update(updated_at=now)
                dispatch.enqueue_email(job.id)
                stats["emails"] += 1
    if any(stats.values()):
        logger.info("Recovery pass: %s", stats)
    return stats


def _expire(job: Job) -> None:
    from .pipeline import complete_job

    job.error_code = "retention_expired"
    job.error_message = "The job did not finish within the maximum retention period."
    complete_job(job, status=JobStatus.FAILED)


def cleanup_job_work(job_id) -> None:
    """Delete temporary extracted/normalised audio once the job is terminal."""
    job = Job.objects.filter(pk=job_id).first()
    if job is None or not job.is_terminal or job.work_deleted_at:
        return
    storage.remove_tree(storage.work_dir(job.id))
    Job.objects.filter(pk=job.pk).update(work_deleted_at=timezone.now())


def cleanup_storage() -> dict[str, int]:
    """Retention-aware cleanup.

    An archive is deleted only when ALL hold: its minimum retention has passed,
    the job is terminal (no active processing, no pending retry, no recovery
    dependency). Results follow their own, longer retention.
    """
    cfg = get_config()
    now = timezone.now()
    stats = {"archives": 0, "work": 0, "results": 0, "orphans": 0}

    for job in Job.objects.filter(
        archive_deleted_at__isnull=True, archive_retain_until__lt=now, status__in=TERMINAL_JOB_STATUSES,
    ).filter(_lease_free(now)):
        storage.remove_tree(storage.archive_dir(job.id))
        Job.objects.filter(pk=job.pk).update(archive_deleted_at=now)
        stats["archives"] += 1

    for job in Job.objects.filter(work_deleted_at__isnull=True, status__in=TERMINAL_JOB_STATUSES):
        cleanup_job_work(job.id)
        stats["work"] += 1

    for job in Job.objects.filter(results_deleted_at__isnull=True, results_expire_at__lt=now,
                                  status__in=TERMINAL_JOB_STATUSES):
        storage.remove_tree(storage.results_dir(job.id))
        Job.objects.filter(pk=job.pk).update(results_deleted_at=now)
        stats["results"] += 1

    stats["orphans"] = _remove_orphans(cfg, now)
    if any(stats.values()):
        logger.info("Cleanup pass: %s", stats)
    return stats


def _remove_orphans(cfg, now) -> int:
    """Remove archive directories without a job (crash between persist and insert)."""
    root = cfg.storage_dir("archive")
    if not root.is_dir():
        return 0
    min_age = int(cfg.storage["archive"]["retention_seconds"])
    known = {str(j) for j in Job.objects.values_list("id", flat=True)}
    removed = 0
    for child in root.iterdir():
        if child.is_dir() and child.name not in known and time.time() - child.stat().st_mtime > min_age:
            storage.remove_tree(child)
            removed += 1
    return removed
