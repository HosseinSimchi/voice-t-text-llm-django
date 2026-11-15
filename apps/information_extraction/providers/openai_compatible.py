"""Adapter for OpenAI-compatible chat-completions servers.

Works with local servers such as llama.cpp ``llama-server``, vLLM, LM Studio or
LocalAI. It is only used when explicitly configured (``llm.provider:
openai_compatible``); the API key, if any, is read from the environment variable
named in ``llm.api_key_env`` — never from configuration files.
"""

from __future__ import annotations

import os
from typing import Any

from .base import LLMProvider, LLMRequest, LLMRequestError, LLMResponse


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"

    def complete(self, request: LLMRequest) -> LLMResponse:
        base_url = str(self.config.get("base_url") or "http://localhost:8080/v1").rstrip("/")
        headers = {}
        key_env = self.config.get("api_key_env")
        if key_env and os.environ.get(key_env):
            headers["Authorization"] = f"Bearer {os.environ[key_env]}"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
            **{k: v for k, v in self.options.items() if k not in {"structured_output"}},
        }
        if request.json_schema is not None:
            if self.options.get("structured_output", False):
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "extraction", "schema": request.json_schema},
                }
            else:
                payload["response_format"] = {"type": "json_object"}
        data = self._post_json(f"{base_url}/chat/completions", payload, headers)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMRequestError("Provider response did not contain choices[0].message.content.") from exc
        return LLMResponse(content=content or "", model=data.get("model", self.model), raw={"usage": data.get("usage")})
