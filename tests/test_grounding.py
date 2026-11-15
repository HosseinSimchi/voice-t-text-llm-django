"""Grounding: values the transcript does not support are removed (schema-driven, no field names in code)."""

import json

import pytest

from apps.information_extraction.services.engine import ExtractionEngine
from apps.information_extraction.services.grounding import ground
from apps.information_extraction.validators.output import validate_against_schema
from tests.fakes import FakeProvider

ALI = ("سلام به همه. جلسهی امروز را با مورور وزیت پروژه شروع می کنیم. تا پایان حفتهی گذشته حدود 70% از کارها انجام شده است. "
       "پیشنهاد من اینست که تحویل را به پانزده همه آزر ماه مکل کنیم.")
REZA = ("من هم نکتایی دارم. دو خطایی مربود به بارگزاری فایل را همین امروز بررسی کردم. برای رفع مشکل به حدود دو روز کار "
        "نیاز داریم. اما خطای گزارشگیری پیچی دهتر است.")


def test_invented_names_and_placeholders_from_the_real_run_are_removed(cfg):
    data = {"responsible_people": ["همیش"], "organizations_and_people": ["همیش"], "locations": ["نامشخص"],
            "important_dates": ["پانزده همه آزار ماه"], "important_numbers": ["70"]}
    cleaned, removed = ground(data, cfg.extraction_schema, ALI)
    assert cleaned["responsible_people"] == [] and cleaned["organizations_and_people"] == []
    assert cleaned["locations"] == []
    assert cleaned["important_dates"] == ["پانزده همه آزار ماه"]  # ASR/LLM spelling variant is still supported
    assert cleaned["important_numbers"] == ["70"]
    assert removed == {"responsible_people": ["همیش"], "organizations_and_people": ["همیش"], "locations": ["نامشخص"]}


def test_placeholder_owner_becomes_null_but_the_task_is_kept(cfg):
    data = {"action_items": [{"task": "بررسی مشکلات بارگزاری فایل", "owner": "نام نیازمند", "due": "حدود دو روز"}]}
    cleaned, removed = ground(data, cfg.extraction_schema, REZA)
    item = cleaned["action_items"][0]
    assert item == {"task": "بررسی مشکلات بارگزاری فایل", "owner": None, "due": "حدود دو روز"}
    assert removed == {"action_items.owner": ["نام نیازمند"]}


def test_digits_are_matched_across_persian_and_latin_forms(cfg):
    cleaned, removed = ground({"important_numbers": ["۷۰ درصد", "۹۹ نفر"]}, cfg.extraction_schema, "حدود 70 درصد انجام شد")
    assert cleaned["important_numbers"] == ["۷۰ درصد"] and removed["important_numbers"] == ["۹۹ نفر"]


def test_free_text_fields_are_not_touched(cfg):
    data = {"main_topic": "موضوعی که در متن نیست", "key_points": ["جمله‌ای کاملاً متفاوت"]}
    cleaned, removed = ground(data, cfg.extraction_schema, ALI)
    assert cleaned == data and removed == {}


def test_works_for_a_completely_different_schema_without_code_changes():
    schema = {"type": "object", "properties": {
        "customer": {"type": "string", "x-grounded": True},
        "competitors": {"type": "array", "items": {"type": "string"}, "x-grounded": True},
        "pitch": {"type": "string"}}}
    data = {"customer": "شرکت آلفا", "competitors": ["بتا", "گاما"], "pitch": "هر چیزی"}
    cleaned, removed = ground(data, schema, "با شرکت آلفا و رقیب بتا صحبت کردیم")
    assert cleaned == {"customer": "شرکت آلفا", "competitors": ["بتا"], "pitch": "هر چیزی"}
    assert removed == {"competitors": ["گاما"]}


def test_a_non_nullable_unsupported_string_is_kept_but_reported():
    schema = {"type": "object", "properties": {"customer": {"type": "string", "x-grounded": True}}}
    cleaned, removed = ground({"customer": "ناشناس"}, schema, "متن دیگر")
    assert cleaned == {"customer": "ناشناس"} and removed == {"customer": ["ناشناس"]}


def test_engine_removes_invented_values_records_them_and_keeps_the_result_schema_valid(cfg):
    from tests.fakes import sample_for_schema

    answer = sample_for_schema(cfg.extraction_schema)
    answer.update(responsible_people=["همیش", "خانم احمدی"], locations=["نامشخص"],
                  action_items=[{"task": "گزارش", "owner": "نام نیازمند", "due": None}])
    FakeProvider.responses = [json.dumps(answer, ensure_ascii=False)]
    outcome = ExtractionEngine(cfg).extract(transcript="خانم احمدی گزارش نهایی را می دهد", filename="a.mp3")
    assert outcome.data["responsible_people"] == ["خانم احمدی"]
    assert outcome.data["locations"] == [] and outcome.data["action_items"][0]["owner"] is None
    assert outcome.meta["ungrounded_removed"]["responsible_people"] == ["همیش"]
    assert validate_against_schema(outcome.data, cfg.extraction_schema) == []


@pytest.mark.parametrize("name", ["system_prompt.txt"])
def test_system_prompt_forbids_placeholders(name, cfg):
    assert "NEVER fill a field with a placeholder" in cfg.prompts["system"]


def test_a_look_alike_word_in_the_transcript_does_not_support_a_placeholder(cfg):
    """Regression from the real run: «نامشخص» was accepted because the transcript contains «مشخص»."""
    transcript = "علت آن مشخص شده است و پیشنهاد می کنم"
    cleaned, removed = ground({"responsible_people": ["نامشخص"], "locations": ["نامشخص"]}, cfg.extraction_schema,
                              transcript)  # no placeholder list: the stricter matching alone must reject it
    assert cleaned == {"responsible_people": [], "locations": []} and set(removed) == {"responsible_people", "locations"}


def test_configured_placeholders_are_removed_from_every_string_field(cfg):
    data = {"main_topic": "نامشخص", "key_points": ["نکته واقعی", "ذکر نشده"], "locations": ["Unknown"],
            "action_items": [{"task": "کاری", "owner": "نام نیازمند", "due": "N/A"}]}
    cleaned, removed = ground(data, cfg.extraction_schema, "نکته واقعی و کاری",
                              placeholders=cfg.extraction["placeholder_values"])
    assert cleaned["main_topic"] == "" and cleaned["key_points"] == ["نکته واقعی"] and cleaned["locations"] == []
    assert cleaned["action_items"][0] == {"task": "کاری", "owner": None, "due": None}
    assert set(removed) == {"main_topic", "key_points", "locations", "action_items.owner", "action_items.due"}


def test_placeholders_only_match_whole_values_so_real_text_is_kept(cfg):
    data = {"key_points": ["بدون مشکل کار انجام شد", "نامشخص (در متن ذکر نشده است)", "هیچ"]}
    cleaned, _ = ground(data, cfg.extraction_schema, "x", placeholders=cfg.extraction["placeholder_values"])
    assert cleaned["key_points"] == ["بدون مشکل کار انجام شد"]


def test_the_real_extraction_of_the_third_recording_is_cleaned(cfg):
    transcript = ("من هم نکتایی دارم. دو خطایی مربود به بارگزاری فایل را همین امروز بررسی کردم و علت آن مشخص شده است. "
                  "برای رفع مشکل به حدود دو روز کار نیاز داریم.")
    raw = {"responsible_people": ["نامشخص"], "organizations_and_people": ["نامشخص"], "locations": ["نامشخص"],
           "important_dates": ["حدود دو روز"]}
    cleaned, removed = ground(raw, cfg.extraction_schema, transcript, placeholders=cfg.extraction["placeholder_values"])
    assert cleaned == {"responsible_people": [], "organizations_and_people": [], "locations": [],
                       "important_dates": ["حدود دو روز"]}
    assert set(removed) == {"responsible_people", "organizations_and_people", "locations"}
