"""Configuration-driven PDF rendering (one PDF per audio file).

Sections, field order, labels, visibility and timestamps come from
``config/ai/pdf_template.yaml``; extraction fields come from the active JSON
Schema and the validated result, rendered generically by JSON type. Adding a
schema field therefore needs no change here.
"""

from __future__ import annotations

import io
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, SimpleDocTemplate, Spacer

from apps.core.config import RuntimeConfig, get_config, resolve_project_path
from apps.transcription.text import format_timestamp

from .rtl import BidiParagraph, visual

PRIMARY = HexColor("#1e3a8a")
MUTED = HexColor("#475569")
RULE = HexColor("#cbd5e1")

_font_lock = threading.Lock()
_registered: dict[str, str] = {}


@dataclass
class DocumentContext:
    filename: str
    processing_date: datetime
    language: str
    job_id: str
    duration: float | None = None
    stt_model: str = ""
    llm_model: str = ""
    paragraphs: list[dict[str, Any]] = field(default_factory=list)
    extraction: dict[str, Any] | None = None
    extraction_attempted: bool = False


def _register_font(path_str: str, alias_prefix: str) -> str:
    path = resolve_project_path(path_str)
    with _font_lock:
        if str(path) not in _registered:
            name = f"{alias_prefix}-{len(_registered)}"
            pdfmetrics.registerFont(TTFont(name, str(path)))  # TrueType is embedded (subset)
            _registered[str(path)] = name
        return _registered[str(path)]


def _t(value: Any, lang: str) -> str:
    if isinstance(value, dict):
        return value.get(lang) or value.get("en") or value.get("fa") or next(iter(value.values()), "")
    return str(value or "")


class PdfRenderer:
    def __init__(self, cfg: RuntimeConfig | None = None):
        self.cfg = cfg or get_config()
        self.tpl = self.cfg.pdf
        fonts = self.tpl["fonts"]
        self.font = _register_font(fonts["regular"], "Body")
        self.bold = _register_font(fonts.get("bold") or fonts["regular"], "Bold")
        self.size = float(fonts.get("size", 11))
        self.heading_size = float(fonts.get("heading_size", 15))
        self.title_size = float(fonts.get("title_size", 19))
        self.leading = self.size * float(fonts.get("line_spacing", 1.6))
        self.lang = self.tpl.get("document", {}).get("language", "fa")

    # ------------------------------------------------------------------
    def render(self, ctx: DocumentContext) -> bytes:
        doc_cfg = self.tpl.get("document", {})
        margins = doc_cfg.get("margins_mm", {})
        buffer = io.BytesIO()
        title = _t(doc_cfg.get("title", "Transcript"), self.lang)
        doc = SimpleDocTemplate(
            buffer,
            pagesize=LETTER if doc_cfg.get("page_size") == "LETTER" else A4,
            topMargin=float(margins.get("top", 20)) * mm,
            bottomMargin=float(margins.get("bottom", 20)) * mm,
            leftMargin=float(margins.get("left", 18)) * mm,
            rightMargin=float(margins.get("right", 18)) * mm,
            title=f"{title} — {ctx.filename}",
            author=doc_cfg.get("author", ""),
            subject=_t(doc_cfg.get("subject", ""), self.lang),
            creator="Persian Audio Intelligence Platform",
            lang=ctx.language or self.lang,
        )
        story = self.build_story(ctx)

        def on_page(canvas, document):
            canvas.saveState()
            canvas.setFont(self.font, 8.5)
            canvas.setFillColor(MUTED)
            label = "صفحه" if self.lang == "fa" else "Page"
            text = f"{label} {document.page}"
            canvas.drawCentredString(document.pagesize[0] / 2, 10 * mm, visual(text, self.lang == "fa"))
            canvas.restoreState()

        doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
        return buffer.getvalue()

    def build_story(self, ctx: DocumentContext) -> list:
        title = _t(self.tpl.get("document", {}).get("title", "Transcript"), self.lang)
        story: list = [
            BidiParagraph(title, self.bold, self.title_size, self.title_size * 1.5, color=PRIMARY),
            BidiParagraph(ctx.filename, self.font, self.size + 1, self.leading, color=MUTED, space_after=8),
            HRFlowable(width="100%", color=RULE, thickness=0.8, spaceAfter=8),
        ]
        builders = {"metadata": self._metadata, "extraction": self._extraction, "transcript": self._transcript}
        for section in self.tpl.get("sections", ["metadata", "extraction", "transcript"]):
            story.extend(builders[section](ctx))
        return story

    def render_to(self, ctx: DocumentContext, target: Path) -> int:
        from apps.uploads.storage import atomic_write_bytes

        data = self.render(ctx)
        atomic_write_bytes(target, data)
        return len(data)

    # ------------------------------------------------------------------
    def _heading(self, text: str) -> list:
        return [
            Spacer(1, 6),
            BidiParagraph(text, self.bold, self.heading_size, self.heading_size * 1.6, color=PRIMARY,
                          space_after=4),
        ]

    def _body(self, text: str, *, indent: float = 0, color=None, bold: bool = False) -> BidiParagraph:
        kwargs = {"color": color} if color is not None else {}
        return BidiParagraph(text, self.bold if bold else self.font, self.size, self.leading,
                             indent=indent, **kwargs)

    def _metadata(self, ctx: DocumentContext) -> list:
        cfg = self.tpl.get("metadata", {})
        if not cfg.get("visible", True):
            return []
        labels = cfg.get("labels", {})
        values = {
            "filename": ctx.filename,
            "processing_date": ctx.processing_date.strftime("%Y-%m-%d %H:%M"),
            "language": {"fa": "فارسی", "en": "English"}.get(ctx.language, ctx.language) if self.lang == "fa"
            else ctx.language,
            "duration": format_timestamp(ctx.duration) if ctx.duration else "",
            "stt_model": ctx.stt_model,
            "llm_model": ctx.llm_model,
            "job_id": ctx.job_id,
        }
        out = self._heading(_t(cfg.get("title", "Processing details"), self.lang))
        for key in cfg.get("fields", list(values)):
            if values.get(key):
                out.append(self._body(f"{_t(labels.get(key, key), self.lang)}: {values[key]}"))
        return out

    def _transcript(self, ctx: DocumentContext) -> list:
        cfg = self.tpl.get("transcript", {})
        if not cfg.get("visible", True):
            return []
        out = self._heading(_t(cfg.get("title", "Transcript"), self.lang))
        if not ctx.paragraphs:
            out.append(self._body(_t(cfg.get("empty_text", "—"), self.lang), color=MUTED))
            return out
        show_ts = cfg.get("show_timestamps", True)
        for para in ctx.paragraphs:
            if show_ts and para.get("start") is not None:
                stamp = f"[{format_timestamp(para.get('start'))} – {format_timestamp(para.get('end'))}]"
                # Timestamps are LTR content placed on the reading-start side of an RTL page.
                out.append(BidiParagraph(stamp, self.font, self.size - 2, self.leading * 0.8, color=MUTED,
                                         rtl=False, align_right=self.lang == "fa", space_after=0))
            out.append(self._body(para.get("text", "")))
        return out

    # ---- generic, schema-driven extraction rendering --------------------
    def _extraction(self, ctx: DocumentContext) -> list:
        cfg = self.tpl.get("extraction", {})
        if not cfg.get("visible", True) or not self.cfg.extraction_enabled:
            return []
        out = self._heading(_t(cfg.get("title", "Extracted information"), self.lang))
        if ctx.extraction is None:
            out.append(self._body(_t(cfg.get("unavailable_text", "—"), self.lang), color=MUTED))
            return out
        props = self.cfg.extraction_schema.get("properties", {})
        selected = cfg.get("fields", "*")
        keys = list(props) if selected == "*" else list(selected)
        keys += [k for k in ctx.extraction if selected == "*" and k not in props]  # tolerate extra keys
        hide_empty = cfg.get("hide_empty", True)
        labels = cfg.get("labels", {}) or {}
        for key in keys:
            value = ctx.extraction.get(key)
            if hide_empty and _is_empty(value):
                continue
            prop = props.get(key, {})
            label = _t(labels[key], self.lang) if key in labels else prop.get("title") or _humanize(key)
            out.append(self._body(label, bold=True, color=PRIMARY))
            out.extend(self._value(value, prop, indent=8))
            out.append(Spacer(1, 3))
        return out

    def _value(self, value: Any, schema: dict[str, Any], indent: float) -> list:
        if _is_empty(value):
            return [self._body("—", indent=indent, color=MUTED)]
        if isinstance(value, list):
            item_schema = schema.get("items", {}) if isinstance(schema.get("items"), dict) else {}
            return [self._body(f"• {self._inline(v, item_schema)}", indent=indent) for v in value]
        if isinstance(value, dict):
            return [self._body(line, indent=indent) for line in self._pairs(value, schema)]
        return [self._body(self._scalar(value), indent=indent)]

    def _inline(self, value: Any, schema: dict[str, Any]) -> str:
        if isinstance(value, dict):
            return " — ".join(self._pairs(value, schema, first_plain=True))
        if isinstance(value, list):
            return "، ".join(self._inline(v, schema.get("items", {})) for v in value)
        return self._scalar(value)

    def _pairs(self, value: dict, schema: dict[str, Any], first_plain: bool = False) -> list[str]:
        props = schema.get("properties", {})
        order = [k for k in props if k in value] + [k for k in value if k not in props]
        parts = []
        for i, key in enumerate(order):
            if _is_empty(value[key]):
                continue
            text = self._inline(value[key], props.get(key, {}))
            if first_plain and i == 0:
                parts.append(text)
            else:
                parts.append(f"{props.get(key, {}).get('title') or _humanize(key)}: {text}")
        return parts

    def _scalar(self, value: Any) -> str:
        if isinstance(value, bool):
            return ("بله" if value else "خیر") if self.lang == "fa" else ("Yes" if value else "No")
        return str(value)


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _humanize(key: str) -> str:
    return key.replace("_", " ").strip().capitalize()
