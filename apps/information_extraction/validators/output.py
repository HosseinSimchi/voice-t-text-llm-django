"""Parsing and JSON-Schema validation of LLM output (never trusted)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


@dataclass
class ValidationOutcome:
    data: dict[str, Any] | None
    errors: list[str]

    @property
    def valid(self) -> bool:
        return self.data is not None and not self.errors


def _first_json_object(text: str) -> str | None:
    """Return the first balanced {...} block, respecting JSON strings."""
    start = text.find("{")
    while start != -1:
        depth, in_str, escape = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        start = text.find("{", start + 1)
    return None


def parse_json_object(text: str, max_chars: int) -> tuple[dict[str, Any] | None, str | None]:
    if text is None or not text.strip():
        return None, "The response was empty."
    if len(text) > max_chars:
        return None, f"The response exceeded {max_chars} characters."
    candidate = text.strip()
    fence = _FENCE.match(candidate)
    if fence:
        candidate = fence.group(1)
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        block = _first_json_object(candidate)
        if block is None:
            return None, "The response did not contain a JSON object."
        try:
            data = json.loads(block)
        except json.JSONDecodeError as exc:
            return None, f"The response was not valid JSON: {exc.msg}"
    if not isinstance(data, dict):
        return None, "The response JSON must be an object."
    return data, None


def validate_against_schema(data: dict[str, Any], schema: dict[str, Any], max_errors: int = 20) -> list[str]:
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    return [
        f"{'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message[:300]}"
        for err in errors[:max_errors]
    ]


def parse_and_validate(text: str, schema: dict[str, Any], max_chars: int) -> ValidationOutcome:
    data, error = parse_json_object(text, max_chars)
    if error:
        return ValidationOutcome(None, [error])
    errors = validate_against_schema(data, schema)
    return ValidationOutcome(data if not errors else None, errors)
