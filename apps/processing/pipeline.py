"""Pipeline orchestration (business logic; Celery tasks are thin wrappers).

Job-level stages:   ARCHIVE_EXTRACTION -> FILE_PROCESSING -> EMAIL_DELIVERY -> DONE
File-level stages:  preprocess -> transcribe -> PDF -> LLM extraction -> final PDF

Every stage persists its result before the next one starts and is skipped when
already done, so any task can be re-run safely (idempotency) after a crash or a
retry. Leases prevent two workers from running the same job/file at once.
Follow-up dispatches are executed only after the lease is released.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Callable

import rarfile
from django.db import transaction
from django.utils import timezone

from apps.core.config import get_config
from apps.core.exceptions import ArchiveValidationError, PipelineError, TransientError
from apps.uploads import storage
from apps.uploads.archives import Limits, iter_extract

from . import dispatch, leases
from .messages import error_text
from .models import (
    TERMINAL_FILE_STATUSES, AudioFile, EmailStatus, FileStatus, Job, JobStage, JobStatus, StageStatus,
)

logger = logging.getLogger(__name__)
Action = Callable[[], None]


def _run(actions: list[Action]) -> None:
    for action in actions:
        action()


# ==========================================================================
# Job level
# ==========================================================================
def run_job(job_id) -> None:
    job = Job.objects.filter(pk=job_id).first()
    if job is None or job.is_terminal:
        return
    actions: list[Action] = []
    with leases.leased(Job, job_id) as owner:
        if not owner:
            logger.info("Job %s is already being handled by another worker", job_id)
            return
        job.refresh_from_db()
        if job.stage == JobStage.ARCHIVE_EXTRACTION:
            actions += _extract_archive(job)
        if job.stage == JobStage.FILE_PROCESSING:
            actions += _dispatch_pending_files(job)
        elif job.stage == JobStage.EMAIL_DELIVERY and job.email_status in (
            EmailStatus.PENDING, EmailStatus.RETRYING, EmailStatus.SENDING,
        ):
            actions.append(lambda: dispatch.enqueue_email(job.id))
    _run(actions)


def _extract_archive(job: Job) -> list[Action]:
    cfg = get_config()
    archive = storage.archive_abspath(job.archive_path)
    if job.archive_deleted_at or not archive.is_file():
        return _finish_without_files(job, "archive_missing", "The stored archive is no longer available.")

    job.status = JobStatus.EXTRACTING
    job.save(update_fields=["status", "updated_at"])
    extracted_dir = storage.work_dir(job.id) / "extracted"
    try:
        storage.remove_tree(extracted_dir)  # restart extraction from scratch (no file has progressed yet)
        AudioFile.objects.filter(job=job).delete()
        results = list(iter_extract(archive, job.archive_format, extracted_dir,
                                    Limits.from_config(cfg.uploads), cfg.uploads.get("rar_tool", "auto")))
    except ArchiveValidationError as exc:
        return _finish_without_files(job, exc.code, str(exc))
    except (OSError, rarfile.Error) as exc:
        logger.warning("Archive extraction for job %s failed: %s", job.id, exc)
        return _retry_job_stage(job, TransientError("Archive extraction failed temporarily.",
                                                    code="extraction_io_error"))

    with transaction.atomic():
        for res in results:
            AudioFile.objects.create(
                job=job, index=res.index, original_name=res.display_name, extension=res.extension,
                supported=res.path is not None,
                stored_path=storage.relative_to_kind("work", res.path) if res.path else "",
                size_bytes=res.size,
                status=FileStatus.PENDING if res.path else FileStatus.SKIPPED,
                error_code="" if res.path else res.reject_reason,
                error_message="" if res.path else error_text(res.reject_reason, "en"),
                transcript_status=StageStatus.PENDING if res.path else StageStatus.SKIPPED,
                pdf_status=StageStatus.PENDING if res.path else StageStatus.SKIPPED,
                extraction_status=StageStatus.PENDING if res.path else StageStatus.SKIPPED,
            )
        job.stage = JobStage.FILE_PROCESSING
        job.status = JobStatus.TRANSCRIBING
        job.extracted_at = timezone.now()
        job.attempts = 0
        job.next_attempt_at = None
        job.save()
    logger.info("Job %s: extracted %d entries (%d supported)", job.id, len(results),
                sum(1 for r in results if r.path))
    return []


def _finish_without_files(job: Job, code: str, message: str) -> list[Action]:
    job.error_code, job.error_message = code, message[:1000]
    job.stage = JobStage.FILE_PROCESSING
    job.save()
    return []  # _dispatch_pending_files finds nothing to do and finalises the job


def _retry_job_stage(job: Job, exc: PipelineError) -> list[Action]:
    cfg = get_config()
    job.attempts += 1
    if job.attempts >= int(cfg.retry_policy["max_attempts"]):
        return _finish_without_files(job, exc.code, str(exc))
    delay = cfg.backoff_delay(job.attempts)
    job.status = JobStatus.RETRYING
    job.retry_count += 1
    job.next_attempt_at = timezone.now() + timedelta(seconds=delay)
    job.error_code, job.error_message = exc.code, str(exc)[:1000]
    job.save()
    return [lambda: dispatch.enqueue_job(job.id, countdown=delay)]


def _dispatch_pending_files(job: Job) -> list[Action]:
    pending = list(job.files.exclude(status__in=TERMINAL_FILE_STATUSES).values_list("id", flat=True))
    if not pending:
        return [lambda: finalize_job(job.id)]
    return [lambda fid=fid: dispatch.enqueue_file(fid) for fid in pending]


# ==========================================================================
# File level
# ==========================================================================
def process_file(file_id) -> None:
    f = AudioFile.objects.select_related("job").filter(pk=file_id).first()
    if f is None or f.is_terminal or f.job.is_terminal:
        return
    actions: list[Action] = []
    with leases.leased(AudioFile, file_id) as owner:
        if not owner:
            logger.info("File %s is already being processed by another worker", file_id)
            return
        f.refresh_from_db()
        if f.is_terminal:
            return
        actions = _process_file_locked(f, owner)
        if f.is_terminal:
            actions.append(lambda: on_file_terminal(f.job_id))
    _run(actions)


_STAGE_ORDER = ["preprocess", "transcribe", "pdf", "extract", "final_pdf"]


def _process_file_locked(f: AudioFile, owner: str) -> list[Action]:
    while True:
        stage = "preprocess"
        try:
            for stage in _STAGE_ORDER:
                _STAGES[stage](f)
                leases.renew(AudioFile, f.pk, owner)
            _finish_file(f)
            return []
        except Exception as exc:  # noqa: BLE001 - every failure is classified below
            retry = _handle_file_error(f, stage, exc)
            if retry is not None:
                return retry
            if f.is_terminal:
                return []
            # Extraction failed permanently: loop to finish the file with its transcript PDF.


def _set_status(f: AudioFile, status: str) -> None:
    f.status = status
    f.save(update_fields=["status", "updated_at"])
    _sync_job_status(f.job_id)


def _stage_preprocess(f: AudioFile) -> None:
    if f.transcript_status == StageStatus.DONE:
        return
    if f.normalized_path and storage.work_abspath(f.normalized_path).is_file():
        return
    from apps.transcription.audio import normalize, validate_audio

    cfg = get_config()
    _set_status(f, FileStatus.PREPROCESSING)
    src = storage.work_abspath(f.stored_path)
    if not src.is_file():
        raise PipelineError("The extracted audio file is missing.", code="source_missing")
    max_duration = float(cfg.uploads["max_audio_duration_seconds"])
    info = validate_audio(src, max_duration)
    dst = storage.work_dir(f.job_id) / "normalized" / f"{f.index:04d}.wav"
    normalize(src, dst, cfg.stt.get("preprocessing", {}) or {}, max_duration)
    f.duration_seconds = round(info.duration, 2)
    f.audio_codec = info.codec[:64]
    f.normalized_path = storage.relative_to_kind("work", dst)
    f.save(update_fields=["duration_seconds", "audio_codec", "normalized_path", "updated_at"])


def _stage_transcribe(f: AudioFile) -> None:
    if f.transcript_status == StageStatus.DONE:
        return
    from apps.transcription.engine import get_engine

    cfg = get_config()
    _set_status(f, FileStatus.TRANSCRIBING)
    result = get_engine(cfg.stt).transcribe(storage.work_abspath(f.normalized_path))
    f.transcript_segments = result.segments
    f.transcript_paragraphs = result.paragraphs
    f.transcript_text = result.text
    f.transcript_language = (result.language or cfg.stt.get("language") or "")[:16]
    f.transcript_language_probability = result.language_probability
    f.stt_model = str(result.model)[:128]
    if result.duration and not f.duration_seconds:
        f.duration_seconds = round(result.duration, 2)
    f.transcript_status = StageStatus.DONE
    f.attempts = 0
    f.save()


def _render_pdf(f: AudioFile, with_extraction: bool) -> None:
    from apps.document_generation.renderer import DocumentContext, PdfRenderer

    cfg = get_config()
    ctx = DocumentContext(
        filename=f.original_name,
        processing_date=timezone.localtime(),
        language=f.transcript_language or cfg.language,
        job_id=str(f.job_id),
        duration=f.duration_seconds,
        stt_model=f.stt_model,
        llm_model=(f.extraction_meta or {}).get("model", "") if with_extraction else "",
        paragraphs=f.transcript_paragraphs,
        extraction=f.extraction_result if with_extraction else None,
        extraction_attempted=with_extraction,
    )
    target = storage.results_dir(f.job_id) / f"{f.id}.pdf"
    size = PdfRenderer(cfg).render_to(ctx, target)
    f.pdf_path = storage.relative_to_kind("results", target)
    f.pdf_size = size
    f.pdf_status = StageStatus.DONE
    f.pdf_includes_extraction = with_extraction
    f.pdf_generated_at = timezone.now()
    f.attempts = 0
    f.save()


def _stage_pdf(f: AudioFile) -> None:
    if f.pdf_status == StageStatus.DONE and storage.results_abspath(f.pdf_path).is_file():
        return
    _set_status(f, FileStatus.GENERATING_PDF)
    _render_pdf(f, with_extraction=f.extraction_status == StageStatus.DONE)


def _stage_extract(f: AudioFile) -> None:
    cfg = get_config()
    if f.extraction_status != StageStatus.PENDING:
        return
    if not cfg.extraction_enabled:
        f.extraction_status = StageStatus.SKIPPED
        f.save(update_fields=["extraction_status", "updated_at"])
        return
    from apps.information_extraction.services.engine import ExtractionEngine

    _set_status(f, FileStatus.EXTRACTING_INFORMATION)
    outcome = ExtractionEngine(cfg).extract(
        transcript=f.transcript_text, filename=f.original_name, segments=f.transcript_segments,
    )
    f.extraction_result = outcome.data
    f.extraction_meta = outcome.meta
    f.extraction_status = StageStatus.DONE
    f.attempts = 0
    f.save()


def _stage_final_pdf(f: AudioFile) -> None:
    if f.extraction_status == StageStatus.DONE and not f.pdf_includes_extraction:
        _set_status(f, FileStatus.GENERATING_PDF)
        _render_pdf(f, with_extraction=True)


_STAGES = {
    "preprocess": _stage_preprocess,
    "transcribe": _stage_transcribe,
    "pdf": _stage_pdf,
    "extract": _stage_extract,
    "final_pdf": _stage_final_pdf,
}


def _finish_file(f: AudioFile) -> None:
    cfg = get_config()
    extraction_ok = f.extraction_status in (StageStatus.DONE, StageStatus.SKIPPED) or not cfg.extraction_required
    f.status = FileStatus.COMPLETED if extraction_ok else FileStatus.PARTIALLY_COMPLETED
    f.next_attempt_at = None
    f.save()
    logger.info("File %s of job %s finished: %s", f.index, f.job_id, f.status)


def _handle_file_error(f: AudioFile, stage: str, exc: Exception) -> list[Action] | None:
    """Return follow-up actions when a retry was scheduled, else None (failure recorded)."""
    cfg = get_config()
    known = isinstance(exc, PipelineError)
    transient = getattr(exc, "transient", False) or not known
    code = exc.code if known else "internal_error"
    message = str(exc) if known else "An unexpected error occurred while processing this file."
    if known:
        logger.warning("File %s (job %s) stage %s failed [%s]: %s", f.index, f.job_id, stage, code, exc)
    else:
        logger.exception("File %s (job %s) stage %s raised an unexpected error", f.index, f.job_id, stage)

    f.refresh_from_db()
    f.error_code, f.error_message = code[:64], message[:1000]
    if transient:
        kind = "extraction" if stage == "extract" else "default"
        f.attempts += 1
        if f.attempts < int(cfg.retry_for(kind)["max_attempts"]):
            delay = cfg.backoff_delay(f.attempts, kind)
            f.status = FileStatus.RETRYING
            f.next_attempt_at = timezone.now() + timedelta(seconds=delay)
            f.save()
            Job.objects.filter(pk=f.job_id).update(retry_count=_inc("retry_count"))
            _sync_job_status(f.job_id)
            return [lambda: dispatch.enqueue_file(f.id, countdown=delay)]

    f.attempts = 0
    f.next_attempt_at = None
    if stage == "extract":
        f.extraction_status = StageStatus.FAILED
        f.extraction_meta = {**(f.extraction_meta or {}), "error": code,
                             "validation_errors": getattr(exc, "errors", [])[:10]}
        f.save()
        return None
    f.status = FileStatus.FAILED
    if stage == "transcribe":
        f.transcript_status = StageStatus.FAILED
    if stage in ("pdf", "final_pdf") and f.pdf_status != StageStatus.DONE:
        f.pdf_status = StageStatus.FAILED
    if stage == "final_pdf" and f.pdf_status == StageStatus.DONE:
        f.status = FileStatus.PARTIALLY_COMPLETED  # transcript PDF exists; preserve it
    f.save()
    return None


def _inc(field: str):
    from django.db.models import F

    return F(field) + 1


def _sync_job_status(job_id) -> None:
    """Reflect the most relevant active file stage on the job (display only)."""
    statuses = set(AudioFile.objects.filter(job_id=job_id).exclude(
        status__in=TERMINAL_FILE_STATUSES).values_list("status", flat=True))
    if not statuses:
        return
    for candidate, job_status in (
        (FileStatus.PREPROCESSING, JobStatus.TRANSCRIBING),
        (FileStatus.TRANSCRIBING, JobStatus.TRANSCRIBING),
        (FileStatus.PENDING, JobStatus.TRANSCRIBING),
        (FileStatus.GENERATING_PDF, JobStatus.GENERATING_PDF),
        (FileStatus.EXTRACTING_INFORMATION, JobStatus.EXTRACTING_INFORMATION),
        (FileStatus.RETRYING, JobStatus.RETRYING),
    ):
        if candidate in statuses:
            Job.objects.filter(pk=job_id, stage=JobStage.FILE_PROCESSING).update(status=job_status)
            return


def on_file_terminal(job_id) -> None:
    if AudioFile.objects.filter(job_id=job_id).exclude(status__in=TERMINAL_FILE_STATUSES).exists():
        return
    finalize_job(job_id)


# ==========================================================================
# Finalisation
# ==========================================================================
def compute_outcome(job: Job) -> str:
    supported = [f for f in job.files.all() if f.supported]
    if not supported:
        return JobStatus.FAILED
    with_pdf = [f for f in supported if f.has_pdf and f.status in (FileStatus.COMPLETED,
                                                                  FileStatus.PARTIALLY_COMPLETED)]
    if not with_pdf:
        return JobStatus.FAILED
    if all(f.status == FileStatus.COMPLETED for f in supported):
        return JobStatus.COMPLETED
    return JobStatus.PARTIALLY_COMPLETED


def finalize_job(job_id) -> None:
    claimed = Job.objects.filter(pk=job_id, stage=JobStage.FILE_PROCESSING).update(
        stage=JobStage.EMAIL_DELIVERY, status=JobStatus.SENDING_EMAIL)
    if not claimed:
        return  # already finalised by a concurrent file task
    job = Job.objects.get(pk=job_id)
    outcome = compute_outcome(job)
    if outcome == JobStatus.FAILED and not job.error_code:
        job.error_code = "no_file_processed"
        job.error_message = "None of the audio files could be processed."
    email_cfg = get_config().email
    required = (
        outcome == JobStatus.COMPLETED
        or (outcome == JobStatus.PARTIALLY_COMPLETED and email_cfg.get("send_partial_results", True))
        or (outcome == JobStatus.FAILED and email_cfg.get("send_failure_notice", True))
    )
    job.outcome = outcome
    if required:
        job.email_status = EmailStatus.PENDING
        job.save()
        dispatch.enqueue_email(job.id)
    else:
        job.email_status = EmailStatus.NOT_REQUIRED
        job.save()
        complete_job(job)


def complete_job(job: Job, status: str | None = None) -> None:
    cfg = get_config()
    now = timezone.now()
    job.status = status or job.outcome or JobStatus.FAILED
    job.stage = JobStage.DONE
    job.completed_at = now
    job.next_attempt_at = None
    job.results_expire_at = now + timedelta(seconds=int(cfg.storage["results"]["retention_seconds"]))
    job.save()
    logger.info("Job %s finished with status %s", job.id, job.status)
    dispatch.enqueue("processing.cleanup_job_work", job.id)
