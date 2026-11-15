"""Provider abstraction. Adapters translate a generic request into a provider API call."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from apps.core.exceptions import PermanentError, TransientError


class LLMUnavailableError(TransientError):
    """The LLM service could not be reached or timed out."""

    code = "llm_unavailable"


class LLMRequestError(PermanentError):
    """The LLM provider rejected the request (bad model name, invalid parameters...)."""

    code = "llm_request_rejected"


@dataclass
class ChatMessage:
    role: str  # system | user | assistant
    content: str


@dataclass
class LLMRequest:
    messages: list[ChatMessage]
    json_schema: dict[str, Any] | None = None
    temperature: float = 0.2
    max_output_tokens: int = 2048
    max_context_length: int = 8192


@dataclass
class LLMResponse:
    content: str
    model: str
    raw: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Base class for adapters. ``config`` is the ``llm`` section of settings.yaml."""

    name = "base"

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.model = config["model"]
        self.timeout = float(config.get("timeout", 300))
        self.options = dict(config.get("options") or {})

    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse: ...

    def healthcheck(self) -> tuple[bool, str]:
        """Cheap preflight: is the service reachable and is the configured model usable?

        Adapters override this. The default reports "not checked" so custom providers keep working.
        """
        return True, "health check not implemented by this provider"

    def _get_json(self, url: str) -> dict:
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=min(self.timeout, 10)) as resp:  # noqa: S310
                return json.loads(resp.read(2 * 1024 * 1024).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise LLMUnavailableError(f"LLM provider returned HTTP {exc.code}.") from exc
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
            raise LLMUnavailableError(
                f"LLM provider at {_host_of(url)} is unreachable: {_describe_network_error(exc)}"
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LLMUnavailableError("LLM provider returned a non-JSON HTTP body.") from exc

    # Shared HTTP helper (stdlib only — no extra dependency).
    def _post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - configured URL
                raw = resp.read(8 * 1024 * 1024 + 1)
        except urllib.error.HTTPError as exc:
            detail = exc.read(2000).decode("utf-8", "replace")
            if exc.code in (408, 429) or exc.code >= 500:
                raise LLMUnavailableError(f"LLM provider returned HTTP {exc.code}: {detail[:300]}") from exc
            raise LLMRequestError(f"LLM provider rejected the request (HTTP {exc.code}): {detail[:300]}") from exc
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
            raise LLMUnavailableError(
                f"LLM provider at {_host_of(url)} is unreachable: {_describe_network_error(exc)}"
            ) from exc
        if len(raw) > 8 * 1024 * 1024:
            raise LLMRequestError("LLM provider response exceeded 8 MB.")
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LLMUnavailableError("LLM provider returned a non-JSON HTTP body.") from exc


def _host_of(url: str) -> str:
    """scheme://host:port only (never the path or query)."""
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _describe_network_error(exc: BaseException) -> str:
    """A short, actionable reason: refused / timed out / permission denied / DNS ..."""
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return "timed out (the model may still be loading or the machine is out of memory)"
    if isinstance(reason, ConnectionRefusedError):
        return "connection refused (is the LLM server running?)"
    if isinstance(reason, PermissionError):
        return "access denied by the operating system (blocked or reserved port?)"
    if isinstance(reason, socket.gaierror):
        return "host name could not be resolved"
    return type(reason).__name__
