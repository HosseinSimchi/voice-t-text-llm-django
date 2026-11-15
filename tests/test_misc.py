from apps.core.logging import redact
from apps.transcription.text import build_paragraphs, format_timestamp, normalize_persian


def test_logging_redacts_emails_and_tokens():
    out = redact("send to someone@example.com token=abc123 Authorization: Bearer xyz")
    assert "someone@" not in out and "abc123" not in out


def test_persian_normalisation():
    assert normalize_persian("علي  كتاب ميخواند .") == "علی کتاب میخواند."


def test_paragraphs_split_on_pauses_and_keep_order():
    segs = [{"start": 10, "end": 12, "text": "سوم."}, {"start": 0, "end": 2, "text": "اول."},
            {"start": 2.2, "end": 4, "text": "دوم."}]
    paras = build_paragraphs(segs, max_gap=2.0, max_sentences=6)
    assert [p["text"] for p in paras] == ["اول. دوم.", "سوم."]
    assert paras[0]["start"] == 0


def test_timestamp_format():
    assert format_timestamp(65) == "01:05" and format_timestamp(3725) == "01:02:05"
