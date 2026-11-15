"""Deterministic stand-ins for Whisper and the LLM, selected purely via configuration
(``stt.engine`` / ``llm.provider`` dotted paths) — exactly how a real new engine would be plugged in."""

from __future__ import annotations

import json
from typing import Any

from apps.core.exceptions import TransientError
from apps.information_extraction.providers.base import LLMProvider, LLMRequest, LLMResponse, LLMUnavailableError
from apps.transcription.engine import finalize_result

PERSIAN_SEGMENTS = [
    {"start": 4.0, "end": 7.5, "text": "در این جلسه درباره بودجه سال آینده صحبت شد."},
    {"start": 0.0, "end": 3.8, "text": "سلام، به جلسه هفتگی خوش آمدید."},
    {"start": 11.0, "end": 14.0, "text": "آقای رضایی مسئول تهیه گزارش تا پانزدهم مهر است."},
]


class FakeSTT:
    calls: list[str] = []
    fail_times = 0           # raise a transient error this many times first
    segments = PERSIAN_SEGMENTS

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.model_name = f"fake-{cfg['model']}"

    def transcribe(self, audio_path):
        type(self).calls.append(str(audio_path))
        if type(self).fail_times > 0:
            type(self).fail_times -= 1
            raise TransientError("simulated STT failure", code="stt_temporary")
        return finalize_result([dict(s) for s in type(self).segments], "fa", 0.99, 15.0, self.model_name, self.cfg)

    @classmethod
    def reset(cls):
        cls.calls = []
        cls.fail_times = 0
        cls.segments = PERSIAN_SEGMENTS


def sample_for_schema(schema: dict[str, Any]) -> Any:
    """Build a schema-valid value for any schema (so fakes never hardcode fields)."""
    t = schema.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), "null")
    if "enum" in schema:
        return schema["enum"][0]
    if t == "object":
        props = schema.get("properties", {})
        return {k: sample_for_schema(v) for k, v in props.items()}
    if t == "array":
        return [sample_for_schema(schema.get("items", {"type": "string"}))]
    if t == "integer":
        return 1
    if t == "number":
        return 1.5
    if t == "boolean":
        return True
    if t == "null":
        return None
    return "مقدار نمونه"


class FakeProvider(LLMProvider):
    name = "fake"
    requests: list[LLMRequest] = []
    models: list[str] = []
    responses: list[str] = []   # queued raw responses; when empty a valid sample is returned
    unavailable_times = 0

    def complete(self, request: LLMRequest) -> LLMResponse:
        cls = type(self)
        cls.requests.append(request)
        cls.models.append(self.model)
        if cls.unavailable_times > 0:
            cls.unavailable_times -= 1
            raise LLMUnavailableError("simulated outage")
        if cls.responses:
            return LLMResponse(cls.responses.pop(0), self.model)
        return LLMResponse(json.dumps(sample_for_schema(request.json_schema), ensure_ascii=False), self.model)

    @classmethod
    def reset(cls):
        cls.requests, cls.models, cls.responses, cls.unavailable_times = [], [], [], 0


class AlternateProvider(FakeProvider):
    name = "alternate"
