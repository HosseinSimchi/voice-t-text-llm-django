"""Shared fixtures. Every test runs on a private copy of the real configuration in
which only the STT engine and LLM provider are swapped for fakes — via the
configuration files, exactly as an operator would swap them."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from django.conf import settings

from apps.core import config as core_config
from tests.fakes import FakeProvider, FakeSTT

REAL_CONFIG = Path(settings.BASE_DIR) / "config"


class ConfigEditor:
    def __init__(self, root: Path):
        self.root = root

    def path(self, rel: str) -> Path:
        return self.root / rel

    def edit_yaml(self, rel: str, mutate) -> None:
        p = self.path(rel)
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        mutate(data)
        p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        self.reload()

    def write_json(self, rel: str, data) -> None:
        self.path(rel).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        self.reload()

    def write_text(self, rel: str, text: str) -> None:
        self.path(rel).parent.mkdir(parents=True, exist_ok=True)
        self.path(rel).write_text(text, encoding="utf-8")
        self.reload()

    def reload(self):
        return core_config.reload_config()


@pytest.fixture(autouse=True)
def app_config(tmp_path, settings):
    cfg_dir = tmp_path / "config"
    shutil.copytree(REAL_CONFIG, cfg_dir, ignore=shutil.ignore_patterns("settings", "__pycache__", "*.py"))
    settings.APP_CONFIG_DIR = cfg_dir
    settings.MEDIA_ROOT = tmp_path / "media"
    editor = ConfigEditor(cfg_dir)

    def use_fakes(data):
        data["stt"]["engine"] = "tests.fakes.FakeSTT"

    stt = cfg_dir / "ai" / "stt.yaml"
    data = yaml.safe_load(stt.read_text(encoding="utf-8"))
    use_fakes(data)
    stt.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    ai = cfg_dir / "ai" / "settings.yaml"
    data = yaml.safe_load(ai.read_text(encoding="utf-8"))
    data["llm"]["provider"] = "tests.fakes.FakeProvider"
    data["ai"]["retry"]["delay_seconds"] = 0
    ai.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    app = cfg_dir / "app.yaml"
    data = yaml.safe_load(app.read_text(encoding="utf-8"))
    for key in ("retry", "extraction_retry", "email_retry"):
        data["processing"][key]["initial_delay_seconds"] = 0
    app.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    FakeSTT.reset()
    FakeProvider.reset()
    core_config.reload_config()
    yield editor
    FakeSTT.reset()
    FakeProvider.reset()


@pytest.fixture
def cfg(app_config):
    return core_config.get_config()
