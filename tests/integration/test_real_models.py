"""Optional tests against real local models. Run with:

    RUN_INTEGRATION=1 pytest tests/integration -m integration -s

Requirements: Ollama running with the configured model pulled; network access to
Hugging Face on first run (Whisper weights are downloaded and cached).
Optional: put Persian samples in tests/samples/<name>.wav with <name>.txt reference
transcripts to also run the transcription-quality check (see scripts/evaluate_transcription.py).
"""

import os
from pathlib import Path

import pytest

from apps.core.config import get_config

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("RUN_INTEGRATION") != "1", reason="set RUN_INTEGRATION=1"),
]

PERSIAN_TRANSCRIPT = (
    "سلام به همه. جلسه امروز درباره راه‌اندازی نسخه جدید سامانه فروش است. "
    "تصمیم گرفتیم انتشار نسخه را به بیستم آذر موکول کنیم. "
    "خانم احمدی مسئول تست نهایی است و باید تا پانزدهم آذر گزارش بدهد. "
    "بودجه این فاز دویست میلیون تومان تعیین شد. خطر اصلی کمبود نیروی پشتیبانی در تهران است."
)


@pytest.fixture
def real_models(app_config):
    def llm(d):
        d["llm"]["provider"] = "ollama"
        d["llm"]["base_url"] = os.environ.get("LLM_BASE_URL", "http://localhost:11434")
        d["llm"]["timeout"] = 900

    app_config.edit_yaml("ai/settings.yaml", llm)
    app_config.edit_yaml("ai/stt.yaml", lambda d: d["stt"].update(
        engine="faster_whisper", model=os.environ.get("WHISPER_TEST_MODEL", d["stt"]["model"])))
    return get_config()


def test_ollama_extraction_returns_schema_valid_persian_json(real_models):
    from apps.information_extraction.services.engine import ExtractionEngine
    from apps.information_extraction.validators.output import validate_against_schema

    outcome = ExtractionEngine().extract(transcript=PERSIAN_TRANSCRIPT, filename="meeting.wav", segments=[])
    assert validate_against_schema(outcome.data, real_models.extraction_schema) == []
    print("\nLLM meta:", outcome.meta)
    print("main_topic:", outcome.data.get("main_topic"))
    print("decisions:", outcome.data.get("decisions"))


def test_faster_whisper_loads_and_transcribes(real_models, tmp_path):
    from apps.transcription.engine import get_engine
    from tests.builders import wav_bytes

    sample = tmp_path / "tone.wav"
    sample.write_bytes(wav_bytes(3.0))
    result = get_engine(real_models.stt).transcribe(sample)  # a pure tone: no speech expected
    assert result.model == real_models.stt["model"]
    assert isinstance(result.segments, list)


SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def _has_samples() -> bool:
    exts = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac", ".opus"}
    return any(p.suffix.lower() in exts and p.with_suffix(".txt").is_file() for p in SAMPLES.glob("*"))


@pytest.mark.skipif(not _has_samples(), reason="no Persian audio+reference pairs in tests/samples")
def test_transcription_quality_on_reference_samples(real_models):
    from scripts.evaluate_transcription import evaluate_directory

    report = evaluate_directory(SAMPLES, real_models.stt)
    print("\n", report)
    assert report["files"] > 0
