"""Generic, provider-independent extraction engine.

1. load configuration      (apps.core.config)
2. load the active schema   (cfg.extraction_schema)
3. load external prompts    (cfg.prompts)
4. build the request        (prompts.render)
5. call the provider        (providers.registry)
6. parse + validate output  (validators.output)
7. retry invalid output     (repair prompt with validation errors)
8. return a generic dict    (stored as JSON on the AudioFile)

No extraction field is referenced anywhere in this module.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from apps.core.config import ConfigError, RuntimeConfig, get_config
from apps.core.exceptions import PermanentError

from ..providers.base import ChatMessage, LLMProvider, LLMRequest
from ..providers.registry import build_provider
from ..validators.output import parse_and_validate
from . import grounding, prompts

logger = logging.getLogger(__name__)


class InvalidLLMOutputError(PermanentError):
    """The LLM did not return schema-valid output within the allowed attempts."""

    code = "llm_invalid_output"

    def __init__(self, message: str, errors: list[str]):
        super().__init__(message)
        self.errors = errors


@dataclass
class ExtractionOutcome:
    data: dict[str, Any]
    meta: dict[str, Any] = field(default_factory=dict)


class ExtractionEngine:
    def __init__(self, cfg: RuntimeConfig | None = None, provider: LLMProvider | None = None):
        self.cfg = cfg or get_config()
        self.provider = provider or build_provider(self.cfg.llm)

    @property
    def schema(self) -> dict[str, Any]:
        return self.cfg.extraction_schema

    def _estimate_tokens(self, text: str) -> int:
        """Conservative token estimate (Persian averages roughly 2 characters per token)."""
        return int(len(text) / float(self.cfg.ai.get("chars_per_token", 2.0))) + 1

    def build_messages(self, *, transcript: str, filename: str, segments: list[dict] | None) -> tuple[list[ChatMessage], bool]:
        """Render the prompts, keeping the whole request inside the model's context window.

        A model silently drops the *start* of an over-long prompt (the instructions), so the
        transcript is limited to what fits after the fixed parts (instructions, schema, output
        reservation). The timestamps block repeats transcript content, so it only gets what is left.
        """
        ai, llm = self.cfg.ai, self.cfg.llm
        variables = {
            "transcript": "",
            "filename": prompts.sanitize_transcript(filename, 200)[0],
            "language": self.cfg.language,
            "language_name": self.cfg.language_name,
            "schema": prompts.schema_text(self.schema),
            "field_descriptions": prompts.describe_fields(self.schema),
            "timestamps": "(omitted)",
            "additional_context": self.cfg.extraction.get("additional_context") or "(none)",
            "truncated": "no",
            "validation_errors": "",
        }
        fixed = prompts.render(self.cfg.prompts["system"], variables) + prompts.render(self.cfg.prompts["user"], variables)
        input_budget = int(llm.get("max_context_length", 8192)) - int(llm.get("max_output_tokens", 2048)) - 256
        free_tokens = input_budget - self._estimate_tokens(fixed)
        if free_tokens < 200:
            raise ConfigError(
                "max_context_length is too small for the configured schema and prompts: increase llm.max_context_length "
                "or reduce llm.max_output_tokens / the schema size."
            )
        free_chars = int(free_tokens * float(ai.get("chars_per_token", 2.0)))
        limit = min(int(ai.get("max_transcript_chars", 12000)), free_chars)
        clean, truncated = prompts.sanitize_transcript(transcript, limit)
        left = max(free_chars - len(clean), 0)
        variables["transcript"] = clean
        variables["truncated"] = "yes" if truncated else "no"
        if left >= 200 and segments:
            variables["timestamps"] = prompts.format_timestamps(segments, max_chars=min(3000, left))
        system = prompts.render(self.cfg.prompts["system"], variables)
        user = prompts.render(self.cfg.prompts["user"], variables)
        return [ChatMessage("system", system), ChatMessage("user", user)], truncated

    def extract(self, *, transcript: str, filename: str, segments: list[dict] | None = None) -> ExtractionOutcome:
        messages, truncated = self.build_messages(transcript=transcript, filename=filename, segments=segments)
        retry = self.cfg.ai["retry"]
        max_attempts = int(retry.get("max_attempts", 3))
        delay = float(retry.get("delay_seconds", 0))
        max_chars = int(self.cfg.ai.get("max_response_chars", 60000))
        llm = self.cfg.llm
        errors: list[str] = []
        for attempt in range(1, max_attempts + 1):
            request = LLMRequest(
                messages=list(messages),
                json_schema=self.schema,
                temperature=float(llm.get("temperature", 0.2)),
                max_output_tokens=int(llm.get("max_output_tokens", 2048)),
                max_context_length=int(llm.get("max_context_length", 8192)),
            )
            started = time.monotonic()
            response = self.provider.complete(request)  # LLMUnavailableError propagates (transient)
            outcome = parse_and_validate(response.content, self.schema, max_chars)
            used = int(response.raw.get("prompt_eval_count") or 0)
            window = int(llm.get("max_context_length", 8192))
            if used and used >= window - 8:
                logger.warning("LLM prompt used %d of %d context tokens: the start of the prompt was probably "
                               "truncated by the model; raise llm.max_context_length", used, window)
            if outcome.valid:
                data, removed = grounding.ground(outcome.data, self.schema, transcript,
                                                 placeholders=self.cfg.extraction.get("placeholder_values", []))
                if removed:
                    logger.info("Removed %d value(s) not supported by the transcript in: %s",
                                sum(len(v) for v in removed.values()), ", ".join(sorted(removed)))
                return ExtractionOutcome(data, {
                    "ungrounded_removed": removed,
                    "prompt_tokens": used or None,
                    "output_tokens": response.raw.get("eval_count"),
                    "context_overflow_suspected": bool(used and used >= window - 8),
                    "provider": self.provider.name,
                    "model": response.model or llm["model"],
                    "schema": self.cfg.extraction_schema_name,
                    "schema_sha256": hashlib.sha256(
                        json.dumps(self.schema, sort_keys=True).encode()).hexdigest()[:16],
                    "attempts": attempt,
                    "transcript_truncated": truncated,
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                })
            errors = outcome.errors
            logger.warning("LLM output invalid (attempt %d/%d): %s", attempt, max_attempts, "; ".join(errors[:3]))
            if attempt < max_attempts:
                repair = prompts.render(
                    self.cfg.prompts.get("repair", "Return only valid JSON. Errors: {{ validation_errors }}"),
                    {"validation_errors": "\n".join(f"- {e}" for e in errors)},
                )
                messages = messages[:2] + [
                    ChatMessage("assistant", (response.content or "")[:4000]),
                    ChatMessage("user", repair),
                ]
                if delay:
                    time.sleep(delay)
        raise InvalidLLMOutputError(
            f"The language model did not return valid structured output after {max_attempts} attempts.", errors
        )
