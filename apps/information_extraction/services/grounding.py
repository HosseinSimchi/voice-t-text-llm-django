"""Schema-driven grounding: drop extracted values that the transcript does not support.

Small local models tend to fill empty fields with invented names or placeholders ("unknown",
"name needed"). A schema property marked ``"x-grounded": true`` is checked against the transcript:

* array of strings        -> unsupported items are removed
* string / nullable string -> an unsupported value becomes ``null`` (or is kept and only reported when
                             the schema does not allow null)
* arrays of objects / nested objects are searched recursively, so a nested property can carry the flag.

A value is supported when most of its words appear in the transcript. Matching is fuzzy, because ASR
spelling is imperfect, and digit-insensitive (Persian and Latin digits are equivalent). Nothing here
knows any field name: it only follows the flag in the active schema.
"""

from __future__ import annotations

import difflib
import re
from typing import Any

from apps.transcription.text import normalize_persian

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_SPLIT = re.compile(r"[\s‌‏‎]+")
_STRIP = re.compile(r"[^\w]+", re.UNICODE)
FLAG = "x-grounded"


def _tokens(text: str) -> list[str]:
    cleaned = normalize_persian(str(text)).translate(_DIGITS)
    return [t for t in (_STRIP.sub("", part).lower() for part in _SPLIT.split(cleaned)) if t]


class _Evidence:
    def __init__(self, transcript: str, min_word_similarity: float, min_supported_share: float):
        self.words = sorted(set(_tokens(transcript)))
        self.index = set(self.words)
        self.similarity = min_word_similarity
        self.share = min_supported_share
        self._cache: dict[str, bool] = {}

    def _word_supported(self, word: str) -> bool:
        if word in self._cache:
            return self._cache[word]
        ok = word in self.index or any(
            min(len(word), len(c)) / max(len(word), len(c)) >= 0.7  # «نامشخص» must not match «مشخص»
            for c in difflib.get_close_matches(word, self.words, n=5, cutoff=self.similarity)
        )
        self._cache[word] = ok
        return ok

    def supports(self, value: str) -> bool:
        words = _tokens(value)
        if not words:
            return False
        hits = sum(1 for w in words if self._word_supported(w))
        return hits / len(words) >= self.share


def _allows_null(schema: dict[str, Any]) -> bool:
    t = schema.get("type")
    return t == "null" or (isinstance(t, list) and "null" in t)


_REMARK = re.compile(r"[\(\[（][^\)\]）]*[\)\]）]")


def _is_placeholder(value: str, placeholders: set[str]) -> bool:
    """True when the WHOLE value only says "nothing here" («نامشخص», "unknown", "-"), ignoring a parenthetical remark.

    Whole-value matching keeps legitimate text such as «بدون مشکل» even though «بدون» is configured.
    """
    words = " ".join(_tokens(_REMARK.sub(" ", value)))
    return not words or words in placeholders


def ground(data: Any, schema: dict[str, Any], transcript: str, *, placeholders: list[str] | tuple[str, ...] = (),
           min_word_similarity: float = 0.75, min_supported_share: float = 0.6) -> tuple[Any, dict[str, list[str]]]:
    """Return ``(cleaned_data, removed)`` where ``removed`` maps a schema path to the dropped values.

    ``placeholders`` (configured in settings.yaml) are "no value" markers removed from EVERY string field.
    """
    evidence = _Evidence(transcript, min_word_similarity, min_supported_share)
    marks = {" ".join(_tokens(p)) for p in placeholders if _tokens(p)}
    removed: dict[str, list[str]] = {}

    def walk(value: Any, node: dict[str, Any], path: str) -> Any:
        flagged = bool(node.get(FLAG))
        if isinstance(value, dict):
            props = node.get("properties", {})
            return {k: walk(v, props.get(k, {}), f"{path}.{k}" if path else k) for k, v in value.items()}
        if isinstance(value, list):
            item_node = node.get("items", {}) if isinstance(node.get("items"), dict) else {}
            kept = []
            for item in value:
                if isinstance(item, str) and _is_placeholder(item, marks):
                    removed.setdefault(path, []).append(item)
                elif isinstance(item, str) and (flagged or item_node.get(FLAG)):
                    if evidence.supports(item):
                        kept.append(item)
                    else:
                        removed.setdefault(path, []).append(item)
                else:
                    kept.append(walk(item, item_node, path))
            return kept
        if isinstance(value, str) and value.strip() and _is_placeholder(value, marks):
            removed.setdefault(path, []).append(value)
            return None if _allows_null(node) else ""
        if isinstance(value, str) and flagged and value.strip() and not evidence.supports(value):
            removed.setdefault(path, []).append(value)
            return None if _allows_null(node) else value
        return value

    return walk(data, schema, ""), removed
