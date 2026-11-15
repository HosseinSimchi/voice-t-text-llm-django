"""Read-model helpers: progress and the user-facing outcome of a job."""

from __future__ import annotations

from .messages import (
    EMAIL_FAILED_MESSAGE_FA, FAILED_MESSAGE_FA, NOT_DELIVERED_NOTE_FA, PARTIAL_MESSAGE_FA, SUCCESS_MESSAGE_FA,
    SUCCESS_NOT_DELIVERED_FA, error_text,
)
from .models import EmailStatus, FileStatus, Job, JobStage, JobStatus

_FILE_PROGRESS = {
    FileStatus.PENDING: 0.0,
    FileStatus.PREPROCESSING: 0.1,
    FileStatus.TRANSCRIBING: 0.25,
    FileStatus.GENERATING_PDF: 0.6,
    FileStatus.EXTRACTING_INFORMATION: 0.7,
    FileStatus.RETRYING: 0.3,
}


def progress(job: Job, files=None) -> int:
    if job.is_terminal:
        return 100
    files = list(files if files is not None else job.files.all())
    if job.stage == JobStage.ARCHIVE_EXTRACTION:
        return 2
    supported = [f for f in files if f.supported]
    if not supported:
        return 90
    per_file = sum(1.0 if f.is_terminal else _FILE_PROGRESS.get(f.status, 0.0) for f in supported) / len(supported)
    value = 5 + 85 * per_file
    if job.stage == JobStage.EMAIL_DELIVERY:
        value = 95
    return int(min(99, value))


def counts(files) -> dict[str, int]:
    files = list(files)
    supported = [f for f in files if f.supported]
    return {
        "total_files": len(files),
        "audio_files": len(supported),
        "successful_files": sum(1 for f in supported if f.status == FileStatus.COMPLETED),
        "partial_files": sum(1 for f in supported if f.status == FileStatus.PARTIALLY_COMPLETED),
        "failed_files": sum(1 for f in supported if f.status == FileStatus.FAILED),
        "skipped_files": sum(1 for f in files if f.status == FileStatus.SKIPPED),
    }


def user_message(job: Job) -> dict[str, str]:
    """The final UI message. Success is announced ONLY after SMTP accepted the e-mail."""
    delivered = job.email_status == EmailStatus.SENT and job.email_transport == "smtp"
    if job.status == JobStatus.COMPLETED and job.email_status == EmailStatus.SENT:
        if delivered:
            return {"kind": "success", "text": SUCCESS_MESSAGE_FA}
        # The e-mail was only written to a console/file backend: never claim it was sent.
        return {"kind": "success_local", "text": SUCCESS_NOT_DELIVERED_FA}
    if job.status == JobStatus.PARTIALLY_COMPLETED:
        note = "" if delivered or job.email_status != EmailStatus.SENT else f" {NOT_DELIVERED_NOTE_FA}"
        return {"kind": "partial", "text": PARTIAL_MESSAGE_FA + note}
    if job.status == JobStatus.FAILED:
        if job.error_code == "email_delivery_failed":
            return {"kind": "email_failed", "text": EMAIL_FAILED_MESSAGE_FA}
        detail = error_text(job.error_code, "fa", "")
        return {"kind": "failed", "text": f"{FAILED_MESSAGE_FA} {detail}".strip()}
    return {"kind": "processing", "text": ""}
