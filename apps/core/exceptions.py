"""Error taxonomy shared by all pipeline stages and the API error handler."""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Base class. ``code`` is a stable machine-readable identifier; messages are user-safe."""

    code = "pipeline_error"
    transient = False

    def __init__(self, message: str = "", *, code: str | None = None):
        super().__init__(message or self.__class__.__doc__ or self.code)
        if code:
            self.code = code


class TransientError(PipelineError):
    """A temporary failure; the stage may succeed when retried."""

    code = "transient_error"
    transient = True


class PermanentError(PipelineError):
    """A failure that retrying cannot fix (invalid input, unsupported format...)."""

    code = "permanent_error"


class ArchiveValidationError(PermanentError):
    """The uploaded archive is invalid or unsafe."""

    code = "invalid_archive"


class AudioValidationError(PermanentError):
    """The audio file is invalid, unsupported or exceeds the limits."""

    code = "invalid_audio"


def api_exception_handler(exc, context):
    """Consistent error envelope: {"error": {"code", "message", "details"}}."""
    response = exception_handler(exc, context)
    if response is None:
        if isinstance(exc, PipelineError):
            return Response(
                {"error": {"code": exc.code, "message": str(exc), "details": {}}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        logger.exception("Unhandled API error")
        return Response(
            {"error": {"code": "server_error", "message": "An internal error occurred.", "details": {}}},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    data = response.data
    code = getattr(exc, "default_code", "error")
    if isinstance(data, dict) and "detail" in data and len(data) == 1:
        message, details = str(data["detail"]), {}
    else:
        message, details = "The request is invalid.", data
        code = "validation_error"
    response.data = {"error": {"code": code, "message": message, "details": details}}
    return response
