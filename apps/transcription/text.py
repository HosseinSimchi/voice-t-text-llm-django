"""Persian text normalisation and paragraph construction from timed segments."""

from __future__ import annotations

import re
from typing import Any

# Whisper frequently emits Arabic code points for Persian letters.
_CHAR_MAP = str.maketrans({
    "ي": "ی",  # ARABIC YEH -> FARSI YEH
    "ى": "ی",  # ALEF MAKSURA -> FARSI YEH
    "ك": "ک",  # ARABIC KAF -> KEHEH
    "ـ": "",        # TATWEEL
})
_SPACES = re.compile(r"[ \t ]+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([،؛؟.!:,;?])")
_SENTENCE_END = re.compile(r"[.!؟?]\s*$")


def normalize_persian(text: str) -> str:
    text = (text or "").translate(_CHAR_MAP)
    text = _SPACES.sub(" ", text).strip()
    return _SPACE_BEFORE_PUNCT.sub(r"\1", text)


def format_timestamp(seconds: float | None) -> str:
    if seconds is None:
        return ""
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def build_paragraphs(segments: list[dict[str, Any]], max_gap: float = 2.0, max_sentences: int = 6) -> list[dict]:
    """Group ordered segments into paragraphs on long pauses or after N sentences."""
    paragraphs: list[dict] = []
    current: list[dict] = []
    sentences = 0
    for seg in sorted(segments, key=lambda s: (s.get("start") or 0.0, s.get("end") or 0.0)):
        text = seg.get("text", "").strip()
        if not text:
            continue
        if current:
            gap = (seg.get("start") or 0.0) - (current[-1].get("end") or 0.0)
            if gap >= max_gap or sentences >= max_sentences:
                paragraphs.append(_close(current))
                current, sentences = [], 0
        current.append(seg)
        if _SENTENCE_END.search(text):
            sentences += 1
    if current:
        paragraphs.append(_close(current))
    return paragraphs


def _close(segs: list[dict]) -> dict:
    return {
        "start": segs[0].get("start"),
        "end": segs[-1].get("end"),
        "text": normalize_persian(" ".join(s["text"].strip() for s in segs)),
    }
