from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.config import reload_config
from apps.processing import maintenance
from apps.processing.models import Job, JobStatus
from apps.uploads import storage
from tests.helpers import api_upload

pytestmark = pytest.mark.django_db(transaction=True)


def _job():
    return Job.objects.get(pk=api_upload(APIClient()).json()["job_id"])


def test_archive_kept_for_minimum_retention_even_when_complete():
    job = _job()
    assert job.status == JobStatus.COMPLETED
    maintenance.cleanup_storage()
    job.refresh_from_db()
    assert job.archive_deleted_at is None
    assert storage.archive_abspath(job.archive_path).is_file()


def test_archive_never_deleted_while_processing_or_retry_pending(monkeypatch):
    monkeypatch.setattr("apps.processing.dispatch.enqueue_job", lambda *a, **k: None)
    job = _job()
    past = timezone.now() - timedelta(hours=3)
    Job.objects.filter(pk=job.pk).update(archive_retain_until=past, status=JobStatus.RETRYING,
                                         next_attempt_at=timezone.now() + timedelta(minutes=5))
    maintenance.cleanup_storage()
    assert storage.archive_abspath(job.archive_path).is_file()


def test_archive_deleted_only_after_expiry_when_terminal():
    job = _job()
    Job.objects.filter(pk=job.pk).update(archive_retain_until=timezone.now() - timedelta(seconds=1))
    stats = maintenance.cleanup_storage()
    job.refresh_from_db()
    assert stats["archives"] == 1 and job.archive_deleted_at is not None
    assert not storage.archive_abspath(job.archive_path).exists()
    # Results have their own, longer retention.
    assert storage.results_abspath(job.files.get().pdf_path).is_file()


def test_temporary_work_files_removed_after_completion():
    job = _job()
    job.refresh_from_db()
    assert job.work_deleted_at is not None
    assert not storage.work_dir(job.id).exists()


def test_results_deleted_after_result_retention():
    job = _job()
    Job.objects.filter(pk=job.pk).update(results_expire_at=timezone.now() - timedelta(seconds=1))
    maintenance.cleanup_storage()
    job.refresh_from_db()
    assert job.results_deleted_at is not None
    f = job.files.get()
    assert not storage.results_dir(job.id).exists()
    from tests.helpers import auth  # noqa: F401
    from apps.processing import access

    sig = access.sign_download(f.id, 3600)
    assert APIClient().get(f"/api/v1/results/{f.id}/download/?sig={sig}").status_code == 410


def test_storage_survives_restart_and_job_resumes(monkeypatch):
    monkeypatch.setattr("apps.processing.dispatch.enqueue_job", lambda *a, **k: None)
    job = _job()  # accepted, but "the worker crashed" before running
    monkeypatch.undo()
    reload_config()  # simulated process restart: fresh configuration, same durable storage
    assert storage.archive_abspath(job.archive_path).is_file()
    Job.objects.filter(pk=job.pk).update(updated_at=timezone.now() - timedelta(hours=1))
    maintenance.recover_jobs()
    assert Job.objects.get(pk=job.pk).status == JobStatus.COMPLETED


def test_stuck_job_beyond_max_retention_is_failed(monkeypatch):
    monkeypatch.setattr("apps.processing.dispatch.enqueue_job", lambda *a, **k: None)
    job = _job()
    Job.objects.filter(pk=job.pk).update(uploaded_at=timezone.now() - timedelta(days=30))
    assert maintenance.recover_jobs()["expired"] == 1
    job.refresh_from_db()
    assert job.status == JobStatus.FAILED and job.error_code == "retention_expired"


def test_orphan_archive_directories_are_removed(cfg):
    import os
    import time
    import uuid

    orphan = cfg.storage_dir("archive") / str(uuid.uuid4())
    orphan.mkdir(parents=True)
    old = time.time() - 7200
    os.utime(orphan, (old, old))
    assert maintenance.cleanup_storage()["orphans"] == 1
    assert not orphan.exists()
