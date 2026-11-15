import pytest

from apps.core.config import ConfigError, load_config
from tests.conftest import REAL_CONFIG


def test_shipped_configuration_is_valid():
    cfg = load_config(REAL_CONFIG)
    assert cfg.llm["provider"] == "ollama"
    assert cfg.storage["archive"]["retention_seconds"] >= 3600
    assert "main_topic" in cfg.extraction_schema["properties"]
    assert cfg.stt["language"] == "fa"


def test_missing_prompt_file_is_actionable(app_config):
    app_config.path("ai/prompts/system_prompt.txt").unlink()
    with pytest.raises(ConfigError, match="system_prompt"):
        app_config.reload()


def test_invalid_yaml_is_reported(app_config):
    app_config.path("ai/settings.yaml").write_text("llm: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid YAML"):
        app_config.reload()


def test_unsupported_provider_is_rejected(app_config):
    with pytest.raises(ConfigError, match="Unsupported LLM provider|could not be imported"):
        app_config.edit_yaml("ai/settings.yaml", lambda d: d["llm"].update(provider="does_not_exist"))


def test_invalid_extraction_schema_is_rejected(app_config):
    with pytest.raises(ConfigError, match="not a valid JSON Schema"):
        app_config.write_json("ai/extraction_schema.json", {"type": "object", "properties": {"a": {"type": 5}}})


def test_schema_must_define_properties(app_config):
    with pytest.raises(ConfigError, match="at least one entry"):
        app_config.write_json("ai/extraction_schema.json", {"type": "object", "properties": {}})


def test_unknown_prompt_placeholder_is_rejected(app_config):
    with pytest.raises(ConfigError, match="unknown placeholders"):
        app_config.write_text("ai/prompts/extraction_prompt.txt", "{{ transcript }} {{ secret_var }}")


def test_user_prompt_requires_transcript_placeholder(app_config):
    with pytest.raises(ConfigError, match="transcript"):
        app_config.write_text("ai/prompts/extraction_prompt.txt", "no placeholder here")


def test_pdf_fields_must_exist_in_schema(app_config):
    with pytest.raises(ConfigError, match="not present in the active schema"):
        app_config.edit_yaml("ai/pdf_template.yaml", lambda d: d["extraction"].update(fields=["nope"]))


def test_archive_retention_below_one_hour_is_rejected(app_config):
    with pytest.raises(ConfigError, match="retention_seconds"):
        app_config.edit_yaml("app.yaml", lambda d: d["storage"]["archive"].update(retention_seconds=60))


def test_prompt_path_cannot_escape_config_dir(app_config):
    with pytest.raises(ConfigError, match="must stay inside"):
        app_config.edit_yaml("ai/settings.yaml",
                             lambda d: d["ai"]["extraction"].update(system_prompt="../../etc/passwd"))


def test_backoff_is_exponential_and_capped(app_config):
    app_config.edit_yaml("app.yaml", lambda d: d["processing"]["retry"].update(
        initial_delay_seconds=30, backoff_multiplier=2, max_delay_seconds=100))
    cfg = app_config.reload()
    assert [cfg.backoff_delay(n) for n in (1, 2, 3, 4)] == [30, 60, 100, 100]
