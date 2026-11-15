"""End-to-end pipeline behaviour with eager Celery, fake STT and fake LLM."""

import smtplib
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from apps.processing import maintenance, pipeline
from apps.processing.messages import PARTIAL_MESSAGE_FA, SUCCESS_MESSAGE_FA
from apps.processing.models import (
    AudioFile, EmailStatus, FileStatus, Job, JobStage, JobStatus, StageStatus,
)
from apps.processing.status import user_message
from apps.uploads import storage
from tests.builders import wav_bytes, zip_bytes
from tests.fakes import FakeProvider, FakeSTT
from tests.helpers import api_upload, auth

pytestmark = pytest.mark.django_db(transaction=True)


def _upload(entries=None):
    data = zip_bytes(entries or {"a.wav": wav_bytes(1.0)})
    body = api_upload(APIClient(), data).json()
    return Job.objects.get(pk=body["job_id"]), body["access_token"]


def test_full_success_sends_email_then_completes():
    job, token = _upload({"one.wav": wav_bytes(1), "two.wav": wav_bytes(1)})
    assert job.status == JobStatus.COMPLETED
    assert job.email_status == EmailStatus.SENT
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == ["user@example.com"]
    assert str(job.id) in msg.body
    assert len(msg.attachments) == 1 and msg.attachments[0][2] == "application/zip"  # ONE zip with all PDFs
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(msg.attachments[0][1])) as zf:
        assert len(zf.namelist()) == 2 and all(zf.read(n).startswith(b"%PDF") for n in zf.namelist())  # one PDF per file
    files = list(job.files.all())
    assert all(f.status == FileStatus.COMPLETED and f.pdf_includes_extraction for f in files)
    assert len({f.pdf_path for f in files}) == 2
    assert user_message(job) == {"kind": "success", "text": SUCCESS_MESSAGE_FA}
    status = APIClient().get(f"/api/v1/jobs/{job.id}/", **auth(token)).json()
    assert status["progress"] == 100 and status["message"]["text"] == SUCCESS_MESSAGE_FA


def test_transcript_segments_are_ordered_and_normalised():
    job, _ = _upload()
    f = job.files.get()
    starts = [s["start"] for s in f.transcript_segments]
    assert starts == sorted(starts)
    assert f.transcript_text.startswith("سلام")
    assert "ي" not in f.transcript_text and "ك" not in f.transcript_text


def test_success_message_not_shown_before_email_accepted(settings, monkeypatch):
    sent = {}

    def fake_enqueue_email(job_id, countdown=None):  # simulate a slow e-mail worker
        sent["job"] = job_id

    monkeypatch.setattr("apps.processing.dispatch.enqueue_email", fake_enqueue_email)
    job, token = _upload()
    job.refresh_from_db()
    assert job.status == JobStatus.SENDING_EMAIL and job.outcome == JobStatus.COMPLETED
    assert user_message(job)["kind"] == "processing"
    data = APIClient().get(f"/api/v1/jobs/{job.id}/", **auth(token)).json()
    assert data["state"] == "SENDING_EMAIL" and data["message"]["text"] == ""
    from apps.notifications.services import send_job_email

    send_job_email(job.id)
    job.refresh_from_db()
    assert job.status == JobStatus.COMPLETED
    assert user_message(job)["text"] == SUCCESS_MESSAGE_FA


def test_one_bad_file_does_not_stop_others_partial_completion():
    job, _ = _upload({"good.wav": wav_bytes(1), "broken.wav": b"RIFF\x00\x00\x00\x00WAVEjunkjunkjunk"})
    files = {f.original_name: f for f in job.files.all()}
    assert files["good.wav"].status == FileStatus.COMPLETED
    assert files["broken.wav"].status == FileStatus.FAILED
    assert files["broken.wav"].error_code == "malformed_audio"
    assert job.status == JobStatus.PARTIALLY_COMPLETED
    assert user_message(job)["text"] == PARTIAL_MESSAGE_FA
    assert len(mail.outbox) == 1 and len(mail.outbox[0].attachments) == 1  # a zip holding only the good file's PDF
    assert storage.results_abspath(files["good.wav"].pdf_path).is_file()


def test_unsupported_entries_are_reported_but_job_can_complete():
    job, _ = _upload({"a.wav": wav_bytes(1), "notes.txt": b"x"})
    assert job.status == JobStatus.COMPLETED
    skipped = job.files.get(original_name="notes.txt")
    assert skipped.status == FileStatus.SKIPPED and skipped.error_code == "unsupported_file_type"


def test_total_failure():
    job, _ = _upload({"broken.wav": b"RIFF\x00\x00\x00\x00WAVEjunkjunkjunk"})
    assert job.status == JobStatus.FAILED
    assert user_message(job)["kind"] == "failed"
    assert len(mail.outbox) == 1  # failure notice (configurable)


def test_transient_stt_failure_is_retried_with_backoff():
    FakeSTT.fail_times = 2
    job, _ = _upload()
    f = job.files.get()
    assert f.status == FileStatus.COMPLETED
    assert len(FakeSTT.calls) == 3
    assert job.retry_count == 2


def test_stt_failure_exhausting_retries_fails_file():
    FakeSTT.fail_times = 10
    job, _ = _upload()
    assert len(FakeSTT.calls) == 3  # max_attempts
    assert job.files.get().status == FileStatus.FAILED
    assert job.status == JobStatus.FAILED


def test_llm_unavailable_preserves_transcript_pdf():
    FakeProvider.unavailable_times = 10
    job, _ = _upload()
    f = job.files.get()
    assert f.transcript_status == StageStatus.DONE
    assert f.extraction_status == StageStatus.FAILED
    assert f.status == FileStatus.PARTIALLY_COMPLETED
    assert f.has_pdf and storage.results_abspath(f.pdf_path).is_file()
    assert not f.pdf_includes_extraction
    assert len(FakeSTT.calls) == 1  # retries never repeated transcription
    assert job.status == JobStatus.PARTIALLY_COMPLETED


def test_llm_recovers_after_temporary_outage():
    FakeProvider.unavailable_times = 1
    job, _ = _upload()
    f = job.files.get()
    assert f.status == FileStatus.COMPLETED and f.extraction_status == StageStatus.DONE
    assert len(FakeSTT.calls) == 1


def test_invalid_llm_output_is_repaired_by_retry():
    FakeProvider.responses = ["this is not json", '{"main_topic": 5}']
    job, _ = _upload()
    f = job.files.get()
    assert f.extraction_status == StageStatus.DONE
    assert f.extraction_meta["attempts"] == 3
    repair_msg = FakeProvider.requests[1].messages[-1].content
    assert "rejected" in repair_msg


def test_extraction_optional_does_not_downgrade_job(app_config):
    app_config.edit_yaml("ai/settings.yaml", lambda d: d["ai"]["extraction"].update(required=False))
    FakeProvider.responses = ["bad"] * 10
    job, _ = _upload()
    assert job.files.get().status == FileStatus.COMPLETED
    assert job.status == JobStatus.COMPLETED


def test_extraction_disabled(app_config):
    app_config.edit_yaml("ai/settings.yaml", lambda d: d["ai"]["extraction"].update(enabled=False))
    job, _ = _upload()
    assert job.files.get().extraction_status == StageStatus.SKIPPED
    assert job.status == JobStatus.COMPLETED
    assert FakeProvider.requests == []


def test_tasks_are_idempotent():
    job, _ = _upload()
    f = job.files.get()
    pdf_time = f.pdf_generated_at
    pipeline.process_file(f.id)
    pipeline.run_job(job.id)
    pipeline.finalize_job(job.id)
    f.refresh_from_db()
    assert len(FakeSTT.calls) == 1 and len(FakeProvider.requests) == 1
    assert f.pdf_generated_at == pdf_time
    assert len(mail.outbox) == 1


def test_lease_prevents_concurrent_duplicate_execution():
    from apps.processing import leases

    job, _ = _upload()
    f = job.files.get()
    AudioFile.objects.filter(pk=f.pk).update(status=FileStatus.PENDING)
    owner = leases.acquire(AudioFile, f.pk)
    assert owner and leases.acquire(AudioFile, f.pk) is None
    pipeline.process_file(f.id)  # another worker: must not run
    assert len(FakeSTT.calls) == 1
    leases.release(AudioFile, f.pk, owner)


def test_email_retry_does_not_repeat_previous_stages(monkeypatch):
    from django.core.mail.backends.locmem import EmailBackend

    original = EmailBackend.send_messages
    state = {"fail": 2}

    def flaky(self, messages):
        if state["fail"]:
            state["fail"] -= 1
            raise smtplib.SMTPServerDisconnected("temporary")
        return original(self, messages)

    monkeypatch.setattr(EmailBackend, "send_messages", flaky)
    job, _ = _upload()
    assert job.status == JobStatus.COMPLETED
    assert job.email_attempts == 3 and len(mail.outbox) == 1
    assert len(FakeSTT.calls) == 1 and len(FakeProvider.requests) == 1


def test_permanent_smtp_failure_marks_job_failed_but_keeps_pdfs(monkeypatch):
    from django.core.mail.backends.locmem import EmailBackend

    def refuse(self, messages):
        raise smtplib.SMTPRecipientsRefused({"user@example.com": (550, b"no such user")})

    monkeypatch.setattr(EmailBackend, "send_messages", refuse)
    job, _ = _upload()
    assert job.status == JobStatus.FAILED and job.error_code == "email_delivery_failed"
    assert job.email_attempts == 1
    assert user_message(job)["kind"] == "email_failed"
    assert storage.results_abspath(job.files.get().pdf_path).is_file()


def test_duplicate_email_is_prevented():
    from apps.notifications.services import send_job_email

    job, _ = _upload()
    send_job_email(job.id)
    send_job_email(job.id)
    assert len(mail.outbox) == 1


def test_large_results_use_signed_links(app_config):
    app_config.edit_yaml("app.yaml", lambda d: d["notifications"]["email"].update(max_attachment_total_bytes=10))
    job, _ = _upload()
    msg = mail.outbox[0]
    assert msg.attachments == []
    assert "/api/v1/results/" in msg.body and "sig=" in msg.body


def test_recovery_after_worker_crash_resumes_without_repeating_done_stages(monkeypatch):
    calls = []
    monkeypatch.setattr("apps.processing.dispatch.enqueue_file", lambda fid, countdown=None: calls.append(fid))
    job, _ = _upload()
    job.refresh_from_db()
    f = job.files.get()
    assert f.status == FileStatus.PENDING  # "worker never picked it up" (broker lost the message)
    monkeypatch.undo()

    # Simulate a crash mid-transcription: stale lease + old timestamp.
    past = timezone.now() - timedelta(hours=1)
    AudioFile.objects.filter(pk=f.pk).update(status=FileStatus.TRANSCRIBING, lease_owner="dead-worker",
                                             lease_until=past, updated_at=past)
    stats = maintenance.recover_jobs()
    assert stats["files"] == 1
    job.refresh_from_db()
    assert job.status == JobStatus.COMPLETED
    assert len(FakeSTT.calls) == 1


def test_recovery_of_job_stuck_before_extraction(monkeypatch):
    monkeypatch.setattr("apps.processing.dispatch.enqueue_job", lambda jid, countdown=None: None)
    job, _ = _upload()
    monkeypatch.undo()
    assert Job.objects.get(pk=job.pk).stage == JobStage.ARCHIVE_EXTRACTION
    Job.objects.filter(pk=job.pk).update(updated_at=timezone.now() - timedelta(hours=1))
    maintenance.recover_jobs()
    assert Job.objects.get(pk=job.pk).status == JobStatus.COMPLETED


def test_recovery_does_not_touch_recent_or_scheduled_work(monkeypatch):
    monkeypatch.setattr("apps.processing.dispatch.enqueue_job", lambda jid, countdown=None: None)
    job, _ = _upload()
    assert maintenance.recover_jobs()["jobs"] == 0  # recently updated -> not stale
    Job.objects.filter(pk=job.pk).update(updated_at=timezone.now() - timedelta(hours=1),
                                         next_attempt_at=timezone.now() + timedelta(minutes=5))
    assert maintenance.recover_jobs()["jobs"] == 0  # retry already scheduled


def test_preserved_intermediate_results_after_pdf_loss():
    job, _ = _upload()
    f = job.files.get()
    storage.results_abspath(f.pdf_path).unlink()
    # Simulate an interruption after transcription + extraction but before the final PDF was written.
    Job.objects.filter(pk=job.pk).update(stage=JobStage.FILE_PROCESSING, status=JobStatus.GENERATING_PDF)
    AudioFile.objects.filter(pk=f.pk).update(status=FileStatus.GENERATING_PDF, pdf_includes_extraction=False)
    pipeline.process_file(f.id)
    f.refresh_from_db()
    assert storage.results_abspath(f.pdf_path).is_file()
    assert len(FakeSTT.calls) == 1 and len(FakeProvider.requests) == 1
