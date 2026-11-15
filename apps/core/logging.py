"""Logging filter that redacts e-mail addresses and access tokens."""

import logging
import re

_EMAIL = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_TOKEN = re.compile(r"(token|sig|password|authorization)([=:\s\"']+)([^\s&\"']+)", re.IGNORECASE)


def redact(text: str) -> str:
    text = _EMAIL.sub(r"\1***@\2", text)
    return _TOKEN.sub(r"\1\2[REDACTED]", text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - never break logging
            return True
        redacted = redact(message)
        if redacted != message:
            record.msg, record.args = redacted, ()
        return True


def mask_email(email: str) -> str:
    return redact(email or "")
