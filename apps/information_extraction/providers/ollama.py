"""Ollama adapter (``POST /api/chat``)."""

from __future__ import annotations

from typing import Any

from .base import LLMProvider, LLMRequest, LLMRequestError, LLMResponse, LLMUnavailableError

# Keys of llm.options that are adapter switches rather than Ollama model options.
_ADAPTER_KEYS = {"structured_output", "keep_alive"}


class OllamaProvider(LLMProvider):
    name = "ollama"

    def complete(self, request: LLMRequest) -> LLMResponse:
        base_url = str(self.config.get("base_url") or "http://localhost:11434").rstrip("/")
        model_options: dict[str, Any] = {
            k: v for k, v in self.options.items() if k not in _ADAPTER_KEYS
        }
        model_options.update({
            "temperature": request.temperature,
            "num_ctx": request.max_context_length,
            "num_predict": request.max_output_tokens,
        })
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "stream": False,
            "options": model_options,
        }
        if "keep_alive" in self.options:
            payload["keep_alive"] = self.options["keep_alive"]
        if request.json_schema is not None:
            # Ollama >= 0.5 accepts a JSON schema for constrained decoding; "json" otherwise.
            payload["format"] = request.json_schema if self.options.get("structured_output", True) else "json"
        data = self._post_json(f"{base_url}/api/chat", payload)
        if "error" in data:
            raise LLMRequestError(f"Ollama error: {str(data['error'])[:300]}")
        content = (data.get("message") or {}).get("content")
        if not isinstance(content, str):
            raise LLMRequestError("Ollama response did not contain message content.")
        return LLMResponse(content=content, model=data.get("model", self.model), raw={
            k: data.get(k) for k in ("total_duration", "eval_count", "prompt_eval_count", "done_reason")
        })

    def healthcheck(self) -> tuple[bool, str]:
        base_url = str(self.config.get("base_url") or "http://localhost:11434").rstrip("/")
        try:
            tags = self._get_json(f"{base_url}/api/tags")
        except LLMUnavailableError as exc:
            return False, str(exc)
        names = {m.get("name") for m in tags.get("models", [])} | {m.get("model") for m in tags.get("models", [])}
        wanted = self.model if ":" in self.model else f"{self.model}:latest"
        if wanted not in names:
            return False, (f"Ollama at {base_url} is running but model '{self.model}' is not installed "
                           f"(run: ollama pull {self.model}). Installed: {sorted(n for n in names if n) or 'none'}")
        return True, f"Ollama at {base_url} is reachable and model '{self.model}' is installed"
