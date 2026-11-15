"""Upload use-case: validate, persist durably, create the job, dispatch processing."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import PurePosixPath

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from apps.core.config import get_config
from apps.core.exceptions import ArchiveValidationError
from apps.core.logging import mask_email
from apps.processing import access
from apps.processing.models import Job, JobStage, JobStatus

from . import storage
from .archives import Limits, display_name_for, inspect_archive
from .sniffing import archive_mime_allowed, sniff_archive

logger = logging.getLogger(__name__)


@dataclass
class UploadResult:
    job: Job
    access_token: str
    audio_entries: int
    rejected_entries: int


def validate_upload_metadata(uploaded: UploadedFile) -> str:
    """Cheap checks on name/MIME/size/magic bytes. Returns the archive kind."""
    cfg = get_config()
    uploads = cfg.uploads
    name = uploaded.name or ""
    ext = PurePosixPath(name.replace("\\", "/")).suffix.lower().lstrip(".")
    if ext not in uploads["allowed_archive_extensions"]:
        raise ArchiveValidationError("Only ZIP and RAR archives are accepted.", code="unsupported_archive_type")
    if uploaded.size is not None and uploaded.size > uploads["max_archive_bytes"]:
        raise ArchiveValidationError("The archive exceeds the maximum upload size.", code="archive_too_large")
    if uploaded.size == 0:
        raise ArchiveValidationError("The uploaded file is empty.", code="empty_upload")
    if not archive_mime_allowed(ext, getattr(uploaded, "content_type", "")):
        raise ArchiveValidationError("The file's MIME type does not match a ZIP/RAR archive.",
                                     code="invalid_mime_type")
    uploaded.seek(0)
    header = uploaded.read(16)
    uploaded.seek(0)
    kind = sniff_archive(header)
    if kind is None or kind != ext:
        raise ArchiveValidationError("The file content is not a valid archive of the declared type.",
                                     code="invalid_archive_format")
    return kind


def create_job_from_upload(uploaded: UploadedFile, email: str) -> UploadResult:
    from apps.processing.dispatch import enqueue_job

    cfg = get_config()
    kind = validate_upload_metadata(uploaded)
    job_id = uuid.uuid4()
    rel_path, size, sha256 = storage.persist_archive(
        uploaded.chunks(), job_id, kind, cfg.uploads["max_archive_bytes"]
    )
    try:
        entries = inspect_archive(
            storage.archive_abspath(rel_path), kind, Limits.from_config(cfg.uploads),
            cfg.uploads.get("rar_tool", "auto"),
        )
    except ArchiveValidationError:
        storage.remove_tree(storage.archive_dir(job_id))  # permanently invalid: nothing to retain
        raise

    token = access.generate_token()
    now = timezone.now()
    with transaction.atomic():
        job = Job.objects.create(
            id=job_id,
            access_token_hash=access.hash_token(token),
            email=email,
            original_filename=display_name_for(uploaded.name or f"archive.{kind}"),
            archive_format=kind,
            archive_path=rel_path,
            archive_size=size,
            archive_sha256=sha256,
            uploaded_at=now,
            archive_retain_until=now + timedelta(seconds=cfg.storage["archive"]["retention_seconds"]),
            status=JobStatus.QUEUED,
            stage=JobStage.ARCHIVE_EXTRACTION,
            config_fingerprint=cfg.fingerprint,
        )
        enqueue_job(job.id)
    accepted = sum(1 for e in entries if e.accepted)
    logger.info("Job %s created (%s, %d bytes, %d audio entries) for %s",
                job.id, kind, size, accepted, mask_email(email))
    return UploadResult(job=job, access_token=token, audio_entries=accepted,
                        rejected_entries=len(entries) - accepted)
