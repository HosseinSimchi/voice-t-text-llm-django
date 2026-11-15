"""Versioned REST API (``/api/v1/``). Views only translate HTTP <-> services."""

from __future__ import annotations

import io
import uuid

from django.http import FileResponse, Http404
from django.urls import reverse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ArchiveValidationError
from apps.uploads import storage
from apps.uploads.services import create_job_from_upload

from . import access, results_zip
from .models import AudioFile, Job
from .serializers import JobStatusSerializer, ResultSerializer, UploadResponseSerializer, UploadSerializer

TOKEN_PARAMS = [
    OpenApiParameter("Authorization", OpenApiTypes.STR, OpenApiParameter.HEADER,
                     description="`Bearer <access_token>` returned by the upload endpoint."),
    OpenApiParameter("X-Job-Token", OpenApiTypes.STR, OpenApiParameter.HEADER, required=False),
]


def _error(code: str, message: str, http_status: int, details=None) -> Response:
    return Response({"error": {"code": code, "message": message, "details": details or {}}}, status=http_status)


def get_authorized_job(request, job_id) -> Job:
    """Fetch a job only if the caller holds its token or session grant; else 404 (no IDOR oracle)."""
    try:
        job = Job.objects.get(pk=uuid.UUID(str(job_id)))
    except (ValueError, Job.DoesNotExist):
        raise Http404
    if not access.can_access_job(request, job):
        raise Http404
    return job


class JobCreateView(APIView):
    parser_classes = [MultiPartParser]
    throttle_scope = "uploads"

    @extend_schema(
        request={"multipart/form-data": UploadSerializer},
        responses={202: UploadResponseSerializer},
        summary="Upload a ZIP/RAR archive of audio files",
    )
    def post(self, request):
        serializer = UploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = create_job_from_upload(serializer.validated_data["file"], serializer.validated_data["email"])
        except ArchiveValidationError as exc:
            return _error(exc.code, str(exc), status.HTTP_400_BAD_REQUEST)
        payload = {
            "job_id": str(result.job.id),
            "status": "queued",
            "message": "Your files have been accepted for processing.",
            "access_token": result.access_token,
            "status_url": f"/api/v1/jobs/{result.job.id}/",
            "audio_files": result.audio_entries,
            "rejected_entries": result.rejected_entries,
        }
        return Response(payload, status=status.HTTP_202_ACCEPTED)


class JobStatusView(APIView):
    throttle_scope = "status"

    @extend_schema(parameters=TOKEN_PARAMS, responses={200: JobStatusSerializer}, summary="Job status")
    def get(self, request, job_id):
        job = get_authorized_job(request, job_id)
        return Response(JobStatusSerializer(job).data)


class JobResultsView(APIView):
    throttle_scope = "status"

    @extend_schema(parameters=TOKEN_PARAMS, responses={200: ResultSerializer(many=True)},
                   summary="Per-file results")
    def get(self, request, job_id):
        job = get_authorized_job(request, job_id)
        files = job.files.select_related("job").all()
        return Response({
            "job_id": str(job.id),
            "state": job.status,
            "download_all_url": reverse("api-job-download", args=[job.id]) if results_zip.pdf_files(job) else None,
            "results": ResultSerializer(files, many=True).data,
        })


class ResultDownloadView(APIView):
    throttle_scope = "downloads"

    @extend_schema(
        parameters=TOKEN_PARAMS + [OpenApiParameter("sig", OpenApiTypes.STR, OpenApiParameter.QUERY,
                                                    required=False, description="Signed e-mail link")],
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
        summary="Download the PDF of one audio file",
    )
    def get(self, request, result_id):
        try:
            f = AudioFile.objects.select_related("job").get(pk=uuid.UUID(str(result_id)))
        except (ValueError, AudioFile.DoesNotExist):
            raise Http404
        sig = request.query_params.get("sig")
        allowed = (sig and access.verify_download_signature(sig, f.id)) or access.can_access_job(request, f.job)
        if not allowed:
            raise Http404
        if not f.has_pdf or f.job.results_deleted_at:
            return _error("result_unavailable", "The PDF is not available (not generated yet or expired).",
                          status.HTTP_410_GONE if f.job.results_deleted_at else status.HTTP_404_NOT_FOUND)
        path = storage.results_abspath(f.pdf_path)
        if not path.is_file():
            return _error("result_unavailable", "The PDF is no longer available.", status.HTTP_410_GONE)
        download_name = f"{f.original_name.rsplit('.', 1)[0] or 'transcript'}.pdf"
        response = FileResponse(open(path, "rb"), content_type="application/pdf", as_attachment=True,
                                filename=download_name)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class JobResultsZipView(APIView):
    throttle_scope = "downloads"

    @extend_schema(
        parameters=TOKEN_PARAMS + [OpenApiParameter("sig", OpenApiTypes.STR, OpenApiParameter.QUERY,
                                                    required=False, description="Signed e-mail link")],
        responses={(200, "application/zip"): OpenApiTypes.BINARY},
        summary="Download one ZIP with the PDFs of all successfully processed files",
    )
    def get(self, request, job_id):
        try:
            job = Job.objects.get(pk=uuid.UUID(str(job_id)))
        except (ValueError, Job.DoesNotExist):
            raise Http404
        sig = request.query_params.get("sig")
        if not ((sig and access.verify_zip_signature(sig, job.id)) or access.can_access_job(request, job)):
            raise Http404
        if job.results_deleted_at:
            return _error("result_unavailable", "The results have expired.", status.HTTP_410_GONE)
        files = results_zip.pdf_files(job)
        if not files:
            return _error("result_unavailable", "No PDF is available for this job yet.", status.HTTP_404_NOT_FOUND)
        response = FileResponse(io.BytesIO(results_zip.build(files)), content_type="application/zip",
                                as_attachment=True, filename=results_zip.zip_name(job))
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
