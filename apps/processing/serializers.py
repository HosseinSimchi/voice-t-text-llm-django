from __future__ import annotations

from django.urls import reverse
from rest_framework import serializers

from . import status as job_status
from .messages import error_text
from .models import AudioFile, Job


class UploadSerializer(serializers.Serializer):
    file = serializers.FileField(allow_empty_file=False, use_url=False)
    email = serializers.EmailField(max_length=254)

    def validate_email(self, value: str) -> str:
        if any(c in value for c in "\r\n"):
            raise serializers.ValidationError("Invalid e-mail address.")
        return value.strip()


class UploadResponseSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
    status = serializers.CharField()
    message = serializers.CharField()
    access_token = serializers.CharField(help_text="Shown once. Send as `Authorization: Bearer <token>`.")
    status_url = serializers.CharField()
    audio_files = serializers.IntegerField()
    rejected_entries = serializers.IntegerField()


class JobStatusSerializer(serializers.ModelSerializer):
    job_id = serializers.UUIDField(source="id")
    state = serializers.CharField(source="status")
    current_stage = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    total_audio_files = serializers.SerializerMethodField()
    successful_files = serializers.SerializerMethodField()
    partial_files = serializers.SerializerMethodField()
    failed_files = serializers.SerializerMethodField()
    skipped_files = serializers.SerializerMethodField()
    email_status = serializers.CharField()
    error = serializers.SerializerMethodField()
    message = serializers.SerializerMethodField()
    files = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "job_id", "state", "current_stage", "progress", "total_audio_files", "successful_files",
            "partial_files", "failed_files", "skipped_files", "email_status", "email_transport", "retry_count",
            "uploaded_at", "archive_retain_until", "completed_at", "error", "message", "files",
        ]

    def _files(self, job):
        cache = self.context.setdefault("_files", {})
        if job.pk not in cache:
            cache[job.pk] = list(job.files.all())
        return cache[job.pk]

    def _counts(self, job):
        return job_status.counts(self._files(job))

    def get_current_stage(self, job) -> str:
        return job.stage

    def get_progress(self, job) -> int:
        return job_status.progress(job, self._files(job))

    def get_total_audio_files(self, job) -> int:
        return self._counts(job)["audio_files"]

    def get_successful_files(self, job) -> int:
        return self._counts(job)["successful_files"]

    def get_partial_files(self, job) -> int:
        return self._counts(job)["partial_files"]

    def get_failed_files(self, job) -> int:
        return self._counts(job)["failed_files"]

    def get_skipped_files(self, job) -> int:
        return self._counts(job)["skipped_files"]

    def get_error(self, job) -> dict | None:
        if not job.error_code:
            return None
        return {"code": job.error_code, "message": error_text(job.error_code, "en", job.error_message),
                "message_fa": error_text(job.error_code, "fa", "")}

    def get_message(self, job) -> dict:
        return job_status.user_message(job)

    def get_files(self, job) -> list[dict]:
        return [
            {"result_id": str(f.id), "index": f.index, "filename": f.original_name, "status": f.status,
             "supported": f.supported, "error_code": f.error_code or None,
             "error_message_fa": error_text(f.error_code, "fa", "") if f.error_code else None}
            for f in self._files(job)
        ]


class ResultSerializer(serializers.ModelSerializer):
    result_id = serializers.UUIDField(source="id")
    filename = serializers.CharField(source="original_name")
    transcription = serializers.SerializerMethodField()
    pdf = serializers.SerializerMethodField()
    extraction = serializers.SerializerMethodField()
    error = serializers.SerializerMethodField()

    class Meta:
        model = AudioFile
        fields = ["result_id", "index", "filename", "status", "supported", "duration_seconds",
                  "transcription", "pdf", "extraction", "error"]

    def get_transcription(self, f) -> dict:
        return {"status": f.transcript_status, "language": f.transcript_language or None,
                "model": f.stt_model or None, "characters": len(f.transcript_text or ""),
                "segments": len(f.transcript_segments or [])}

    def get_pdf(self, f) -> dict:
        available = f.has_pdf and not f.job.results_deleted_at
        return {
            "status": f.pdf_status,
            "includes_extraction": f.pdf_includes_extraction,
            "size_bytes": f.pdf_size or None,
            "download_url": reverse("api-result-download", args=[f.id]) if available else None,
        }

    def get_extraction(self, f) -> dict:
        meta = f.extraction_meta or {}
        return {"status": f.extraction_status, "schema": meta.get("schema"), "model": meta.get("model"),
                "provider": meta.get("provider"), "data": f.extraction_result}

    def get_error(self, f) -> dict | None:
        if not f.error_code:
            return None
        return {"code": f.error_code, "message": error_text(f.error_code, "en", f.error_message)}
