"""Rendering of external prompt templates.

Templates use ``{{ variable }}`` placeholders. Substitution is a single pass over
the *template*, so placeholder-like text inside a transcript is never expanded.
Transcripts are untrusted: delimiter look-alikes are stripped so the transcript
cannot close its data block and inject instructions.
"""

from __future__ import annotations

import json
import re
from typing import Any

from apps.transcription.text import format_timestamp

PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
ALLOWED_VARIABLES = {
    "transcript", "filename", "language", "language_name", "schema", "field_descriptions",
    "timestamps", "additional_context", "validation_errors", "truncated",
}
_DELIMITER_LOOKALIKE = re.compile(r"<{2,}|>{2,}|TRANSCRIPT_(START|END)", re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class PromptTemplateError(ValueError):
    pass


def placeholders(template: str) -> set[str]:
    return set(PLACEHOLDER.findall(template))


def check_template(template: str, name: str) -> None:
    unknown = placeholders(template) - ALLOWED_VARIABLES
    if unknown:
        raise PromptTemplateError(
            f"Prompt '{name}' uses unknown placeholders {sorted(unknown)}; allowed: {sorted(ALLOWED_VARIABLES)}"
        )


def render(template: str, variables: dict[str, Any]) -> str:
    def _sub(match: re.Match) -> str:
        key = match.group(1)
        if key not in variables:
            raise PromptTemplateError(f"Prompt variable '{key}' has no value.")
        return str(variables[key])

    return PLACEHOLDER.sub(_sub, template)


def sanitize_transcript(text: str, max_chars: int) -> tuple[str, bool]:
    clean = _CONTROL.sub("", _DELIMITER_LOOKALIKE.sub(" ", text or ""))
    if len(clean) <= max_chars:
        return clean, False
    return clean[:max_chars].rsplit(" ", 1)[0] + " […]", True


def describe_fields(schema: dict[str, Any]) -> str:
    """Human-readable list of fields generated from the active schema (no hardcoded fields)."""
    required = set(schema.get("required", []))
    lines = []
    for key, prop in schema.get("properties", {}).items():
        type_ = prop.get("type", "any")
        if isinstance(type_, list):
            type_ = "|".join(type_)
        if type_ == "array" and isinstance(prop.get("items"), dict):
            item_type = prop["items"].get("type", "any")
            type_ = f"array of {item_type if isinstance(item_type, str) else '|'.join(item_type)}"
        title = prop.get("title", "")
        desc = prop.get("description", "")
        flag = "required" if key in required else "optional"
        lines.append(f"- {key} ({type_}, {flag}){': ' + title if title else ''}{' — ' + desc if desc else ''}")
    return "\n".join(lines)


def format_timestamps(segments: list[dict[str, Any]], max_chars: int = 3000) -> str:
    out, total = [], 0
    for seg in segments:
        clean, _ = sanitize_transcript(seg.get("text", ""), 500)
        line = f"[{format_timestamp(seg.get('start'))}-{format_timestamp(seg.get('end'))}] {clean}"
        total += len(line) + 1
        if total > max_chars:
            out.append("[…]")
            break
        out.append(line)
    return "\n".join(out) if out else "(no timestamps available)"


def schema_text(schema: dict[str, Any]) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=1)
