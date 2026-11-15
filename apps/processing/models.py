"""Database-backed job and per-audio-file state.

The database — not Celery — is the source of truth for progress, retries and
completion. Every stage records its outcome here so it can be resumed after a
crash of Django, Redis, Celery or Docker without repeating finished stages.
"""

from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class JobStatus(models.TextChoices):
    QUEUED = "QUEUED"
    EXTRACTING = "EXTRACTING"
    TRANSCRIBING = "TRANSCRIBING"
    GENERATING_PDF = "GENERATING_PDF"
    EXTRACTING_INFORMATION = "EXTRACTING_INFORMATION"
    SENDING_EMAIL = "SENDING_EMAIL"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"


TERMINAL_JOB_STATUSES = {JobStatus.COMPLETED, JobStatus.PARTIALLY_COMPLETED, JobStatus.FAILED}


class JobStage(models.TextChoices):
    """Which part of the pipeline currently owns the job (drives recovery)."""

    ARCHIVE_EXTRACTION = "ARCHIVE_EXTRACTION"
    FILE_PROCESSING = "FILE_PROCESSING"
    EMAIL_DELIVERY = "EMAIL_DELIVERY"
    DONE = "DONE"


class EmailStatus(models.TextChoices):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    SENDING = "SENDING"
    RETRYING = "RETRYING"
    SENT = "SENT"
    FAILED = "FAILED"


class FileStatus(models.TextChoices):
    PENDING = "PENDING"
    PREPROCESSING = "PREPROCESSING"
    TRANSCRIBING = "TRANSCRIBING"
    GENERATING_PDF = "GENERATING_PDF"
    EXTRACTING_INFORMATION = "EXTRACTING_INFORMATION"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"  # PDF available, required extraction failed
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"  # unsupported / rejected archive entry


TERMINAL_FILE_STATUSES = {
    FileStatus.COMPLETED, FileStatus.PARTIALLY_COMPLETED, FileStatus.FAILED, FileStatus.SKIPPED,
}


class StageStatus(models.TextChoices):
    PENDING = "PENDING"
    DONE = "DONE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class LeaseMixin(models.Model):
    """Short-lived execution lease preventing concurrent duplicate execution."""

    lease_owner = models.CharField(max_length=64, blank=True, default="")
    lease_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class Job(LeaseMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    access_token_hash = models.CharField(max_length=64, editable=False)
    email = models.EmailField(max_length=254)

    # Archive (server-generated location; the original name is display-only).
    original_filename = models.CharField(max_length=255, blank=True, default="")
    archive_format = models.CharField(max_length=8)
    archive_path = models.CharField(max_length=500)
    archive_size = models.BigIntegerField()
    archive_sha256 = models.CharField(max_length=64)
    uploaded_at = models.DateTimeField(default=timezone.now)
    archive_retain_until = models.DateTimeField(help_text="Minimum retention: never deleted before this.")
    archive_deleted_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=32, choices=JobStatus.choices, default=JobStatus.QUEUED, db_index=True)
    stage = models.CharField(max_length=32, choices=JobStage.choices, default=JobStage.ARCHIVE_EXTRACTION)
    outcome = models.CharField(max_length=32, choices=JobStatus.choices, blank=True, default="",
                               help_text="Final status to apply once email delivery has finished.")
    attempts = models.PositiveIntegerField(default=0, help_text="Attempts of the current job-level stage.")
    retry_count = models.PositiveIntegerField(default=0, help_text="Total retries across all stages.")
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.CharField(max_length=1000, blank=True, default="")
    extracted_at = models.DateTimeField(null=True, blank=True)
    config_fingerprint = models.CharField(max_length=32, blank=True, default="")

    email_status = models.CharField(max_length=16, choices=EmailStatus.choices, default=EmailStatus.PENDING)
    email_attempts = models.PositiveIntegerField(default=0)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    email_message_id = models.CharField(max_length=255, blank=True, default="")
    email_last_error = models.CharField(max_length=500, blank=True, default="")
    email_transport = models.CharField(max_length=32, blank=True, default="",
                                       help_text="smtp = handed to a real SMTP server; anything else is not delivered.")

    completed_at = models.DateTimeField(null=True, blank=True)
    results_expire_at = models.DateTimeField(null=True, blank=True)
    results_deleted_at = models.DateTimeField(null=True, blank=True)
    work_deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["stage", "status"])]

    def __str__(self) -> str:
        return f"Job {self.id} [{self.status}]"

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_JOB_STATUSES


class AudioFile(LeaseMixin):
    """One archive entry. Its UUID is the public ``result_id``."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="files")
    index = models.PositiveIntegerField()
    original_name = models.CharField(max_length=255, help_text="Sanitised, display only.")
    extension = models.CharField(max_length=8, blank=True, default="")
    supported = models.BooleanField(default=True)
    stored_path = models.CharField(max_length=500, blank=True, default="")
    size_bytes = models.BigIntegerField(default=0)

    status = models.CharField(max_length=32, choices=FileStatus.choices, default=FileStatus.PENDING, db_index=True)
    attempts = models.PositiveIntegerField(default=0, help_text="Attempts of the current stage.")
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.CharField(max_length=1000, blank=True, default="")

    duration_seconds = models.FloatField(null=True, blank=True)
    audio_codec = models.CharField(max_length=64, blank=True, default="")
    normalized_path = models.CharField(max_length=500, blank=True, default="")

    transcript_status = models.CharField(max_length=16, choices=StageStatus.choices, default=StageStatus.PENDING)
    transcript_text = models.TextField(blank=True, default="")
    transcript_segments = models.JSONField(default=list, blank=True)
    transcript_paragraphs = models.JSONField(default=list, blank=True)
    transcript_language = models.CharField(max_length=16, blank=True, default="")
    transcript_language_probability = models.FloatField(null=True, blank=True)
    stt_model = models.CharField(max_length=128, blank=True, default="")

    pdf_status = models.CharField(max_length=16, choices=StageStatus.choices, default=StageStatus.PENDING)
    pdf_path = models.CharField(max_length=500, blank=True, default="")
    pdf_size = models.BigIntegerField(default=0)
    pdf_includes_extraction = models.BooleanField(default=False)
    pdf_generated_at = models.DateTimeField(null=True, blank=True)

    extraction_status = models.CharField(max_length=16, choices=StageStatus.choices, default=StageStatus.PENDING)
    extraction_result = models.JSONField(null=True, blank=True)
    extraction_meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["index"]
        constraints = [models.UniqueConstraint(fields=["job", "index"], name="unique_file_index_per_job")]

    def __str__(self) -> str:
        return f"AudioFile {self.index} of {self.job_id} [{self.status}]"

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_FILE_STATUSES

    @property
    def has_pdf(self) -> bool:
        return self.pdf_status == StageStatus.DONE and bool(self.pdf_path)
