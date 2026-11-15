from datetime import datetime

from apps.document_generation.renderer import DocumentContext, PdfRenderer
from apps.document_generation.rtl import BidiParagraph, break_lines, is_rtl, visual
from tests.fakes import sample_for_schema


def _ctx(cfg, **kw):
    base = dict(
        filename="جلسه.wav", processing_date=datetime(2026, 11, 14, 10, 30), language="fa", job_id="job-1",
        duration=75.0, stt_model="small",
        paragraphs=[{"start": 0.0, "end": 4.0, "text": "سلام، به جلسه خوش آمدید."},
                    {"start": 5.0, "end": 9.0, "text": "بودجه سال ۱۴۰۵ معادل 250 میلیون تومان است."}],
        extraction=sample_for_schema(cfg.extraction_schema),
    )
    base.update(kw)
    return DocumentContext(**base)


def _texts(story):
    return [f.text for f in story if isinstance(f, BidiParagraph)]


def test_pdf_is_generated_with_embedded_persian_font(cfg):
    data = PdfRenderer(cfg).render(_ctx(cfg))
    assert data.startswith(b"%PDF")
    assert b"FontFile2" in data          # TrueType font program embedded
    assert b"Vazirmatn" in data


def test_long_transcript_spans_multiple_pages(cfg):
    paragraphs = [{"start": i * 10.0, "end": i * 10.0 + 9, "text": "این یک جمله آزمایشی طولانی است. " * 20}
                  for i in range(40)]
    data = PdfRenderer(cfg).render(_ctx(cfg, paragraphs=paragraphs))
    assert data.count(b"/Type /Page\n") + data.count(b"/Type /Page ") + data.count(b"/Type /Page>") >= 3 \
        or data.count(b"/Type /Page") - data.count(b"/Type /Pages") >= 3


def test_rtl_shaping_and_visual_order():
    assert is_rtl("سلام دنیا") and not is_rtl("Hello سلام")
    shown = visual("سلام", True)
    assert all("ﭐ" <= ch <= "﻿" for ch in shown)  # contextual presentation forms
    assert shown[0] != "س"  # reordered: first logical letter is drawn on the right (last)


def test_line_breaking_happens_in_logical_order(cfg):
    PdfRenderer(cfg)  # registers fonts
    font = PdfRenderer(cfg).font
    lines = break_lines("یک دو سه چهار پنج شش هفت هشت نه ده", font, 11, 60)
    assert len(lines) > 1
    assert " ".join(lines) == "یک دو سه چهار پنج شش هفت هشت نه ده"


def test_new_schema_field_is_rendered_without_code_change(app_config):
    schema = {"type": "object", "properties": {
        "customer_mood": {"type": "string", "title": "حال مشتری"},
        "products": {"type": "array", "title": "محصولات",
                     "items": {"type": "object", "properties": {"name": {"type": "string", "title": "نام"},
                                                                "qty": {"type": "integer", "title": "تعداد"}}}},
    }}
    app_config.write_json("ai/extraction_schema.json", schema)
    cfg = app_config.reload()
    texts = _texts(PdfRenderer(cfg).build_story(_ctx(cfg, extraction={
        "customer_mood": "راضی", "products": [{"name": "لپ‌تاپ", "qty": 2}]})))
    assert "حال مشتری" in texts and "راضی" in " ".join(texts)
    assert any("لپ‌تاپ" in t and "تعداد: 2" in t for t in texts)


def test_pdf_configuration_controls_sections_fields_and_labels(app_config):
    def mutate(d):
        d["sections"] = ["extraction"]
        d["extraction"]["fields"] = ["executive_summary", "main_topic"]
        d["extraction"]["labels"] = {"main_topic": {"fa": "عنوان سفارشی", "en": "Custom"}}

    app_config.edit_yaml("ai/pdf_template.yaml", mutate)
    cfg = app_config.reload()
    texts = _texts(PdfRenderer(cfg).build_story(_ctx(cfg)))
    assert "عنوان سفارشی" in texts
    assert texts.index("خلاصه مدیریتی") < texts.index("عنوان سفارشی")  # configured order
    assert "نکات کلیدی" not in texts                                    # not selected
    assert not any("سلام، به جلسه" in t for t in texts)                 # transcript hidden


def test_timestamps_can_be_hidden(app_config):
    app_config.edit_yaml("ai/pdf_template.yaml", lambda d: d["transcript"].update(show_timestamps=False))
    cfg = app_config.reload()
    texts = _texts(PdfRenderer(cfg).build_story(_ctx(cfg)))
    assert not any(t.startswith("[00:00") for t in texts)


def test_missing_extraction_shows_configured_notice(cfg):
    texts = _texts(PdfRenderer(cfg).build_story(_ctx(cfg, extraction=None)))
    assert cfg.pdf["extraction"]["unavailable_text"]["fa"] in texts
