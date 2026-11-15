"""Server-rendered UI. Uploads go through a CSRF-protected endpoint that reuses the upload service."""

from __future__ import annotations

import uuid

from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from rest_framework import status
from rest_framework.authentication import CSRFCheck
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.config import get_config
from apps.core.exceptions import ArchiveValidationError
from apps.processing import access
from apps.processing.messages import (
    EMAIL_FAILED_MESSAGE_FA, FAILED_MESSAGE_FA, PARTIAL_MESSAGE_FA, SUCCESS_MESSAGE_FA,
)
from apps.processing.models import Job
from apps.processing.serializers import UploadSerializer
from apps.uploads.services import create_job_from_upload


def index(request):
    cfg = get_config()
    return render(request, "web/index.html", {
        "max_bytes": cfg.uploads["max_archive_bytes"],
        "max_mb": cfg.uploads["max_archive_bytes"] // (1024 * 1024),
        "audio_exts": ", ".join(cfg.uploads["allowed_audio_extensions"]),
        "archive_exts": ",".join(f".{e}" for e in cfg.uploads["allowed_archive_extensions"]),
    })


def _enforce_csrf(request) -> None:
    check = CSRFCheck(lambda r: None)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise PermissionDenied(f"CSRF failed: {reason}")


class UiUploadView(APIView):
    """Browser upload endpoint: CSRF enforced, job access stored in the session."""

    parser_classes = [MultiPartParser]
    throttle_scope = "uploads"
    schema = None  # UI-only endpoint: excluded from the public OpenAPI schema

    def initial(self, request, *args, **kwargs):
        _enforce_csrf(request._request)
        super().initial(request, *args, **kwargs)

    def post(self, request):
        serializer = UploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = create_job_from_upload(serializer.validated_data["file"], serializer.validated_data["email"])
        except ArchiveValidationError as exc:
            return Response({"error": {"code": exc.code, "message": str(exc), "details": {}}},
                            status=status.HTTP_400_BAD_REQUEST)
        access.grant_session(request._request, result.job.id)
        return Response({
            "job_id": str(result.job.id),
            "status": "queued",
            "message": "Your files have been accepted for processing.",
            "redirect": reverse("web-job", args=[result.job.id]),
            "audio_files": result.audio_entries,
            "rejected_entries": result.rejected_entries,
        }, status=status.HTTP_202_ACCEPTED)


def job_page(request, job_id):
    try:
        job = Job.objects.get(pk=uuid.UUID(str(job_id)))
    except (ValueError, Job.DoesNotExist):
        raise Http404
    sig = request.GET.get("sig")
    if sig:
        if access.verify_job_link(sig, job.id):
            access.grant_session(request, job.id)
            return HttpResponseRedirect(reverse("web-job", args=[job.id]))  # drop the signature from the URL
        raise Http404
    if not access.session_allows(request, job.id):
        raise Http404
    return render(request, "web/job.html", {
        "job": job,
        "status_url": reverse("api-job-status", args=[job.id]),
        "results_url": reverse("api-job-results", args=[job.id]),
        "zip_url": reverse("api-job-download", args=[job.id]),
        "messages_fa": {
            "success": SUCCESS_MESSAGE_FA, "partial": PARTIAL_MESSAGE_FA,
            "failed": FAILED_MESSAGE_FA, "email_failed": EMAIL_FAILED_MESSAGE_FA,
        },
    })
