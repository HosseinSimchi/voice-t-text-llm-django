"""Loading and validation of every external configuration file.

Configuration defines WHAT the platform does (model, provider, schema, prompts,
PDF layout, limits); Python code only defines HOW. Every file is validated when
the application starts so mistakes surface as actionable errors instead of
failing jobs later.

Files (relative to ``settings.APP_CONFIG_DIR``):

* ``app.yaml``               uploads limits, storage/retention, retry policy, email options
* ``ai/stt.yaml``            speech-to-text engine
* ``ai/settings.yaml``       LLM provider/model/parameters, active schema and prompts
* ``ai/<schema>.json``       active extraction JSON Schema
* ``ai/prompts/*.txt``       system / user / repair prompts
* ``ai/pdf_template.yaml``   PDF rendering
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

_LANGUAGE_NAMES = {"fa": "Persian (Farsi)", "en": "English", "ar": "Arabic"}


class ConfigError(ImproperlyConfigured):
    """Raised for any invalid or missing configuration. Message is actionable."""


# --------------------------------------------------------------------------
# Structural schemas for the configuration files themselves. These describe the
# *shape* of the configuration, never the extraction fields.
# --------------------------------------------------------------------------
_POS_INT = {"type": "integer", "minimum": 1}
_NON_NEG_NUM = {"type": "number", "minimum": 0}
_RETRY_POLICY = {
    "type": "object",
    "required": ["max_attempts", "initial_delay_seconds", "backoff_multiplier", "max_delay_seconds"],
    "properties": {
        "max_attempts": _POS_INT,
        "initial_delay_seconds": _NON_NEG_NUM,
        "backoff_multiplier": {"type": "number", "minimum": 1},
        "max_delay_seconds": _NON_NEG_NUM,
    },
}
_I18N_TEXT = {
    "type": "object",
    "properties": {"fa": {"type": "string"}, "en": {"type": "string"}},
    "additionalProperties": {"type": "string"},
}

APP_YAML_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["uploads", "storage", "processing", "notifications"],
    "properties": {
        "uploads": {
            "type": "object",
            "required": [
                "max_archive_bytes", "max_extracted_bytes", "max_file_bytes", "max_files",
                "max_entries", "max_compression_ratio", "max_audio_duration_seconds",
                "allowed_archive_extensions", "allowed_audio_extensions",
            ],
            "properties": {
                "max_archive_bytes": _POS_INT,
                "max_extracted_bytes": _POS_INT,
                "max_file_bytes": _POS_INT,
                "max_files": _POS_INT,
                "max_entries": _POS_INT,
                "max_compression_ratio": {"type": "number", "minimum": 1},
                "max_audio_duration_seconds": {"type": "number", "exclusiveMinimum": 0},
                "allowed_archive_extensions": {
                    "type": "array", "minItems": 1,
                    "items": {"enum": ["zip", "rar"]},
                },
                "allowed_audio_extensions": {
                    "type": "array", "minItems": 1,
                    "items": {"enum": ["mp3", "wav", "m4a", "aac", "ogg", "flac", "opus"]},
                },
                "rar_tool": {"enum": ["auto", "unrar", "7z", "7zz", "bsdtar", "unar"]},
            },
        },
        "storage": {
            "type": "object",
            "required": ["archive", "work", "results", "max_retention_seconds"],
            "properties": {
                "archive": {
                    "type": "object",
                    "required": ["backend", "directory", "retention_seconds"],
                    "properties": {
                        "backend": {"enum": ["local"]},
                        "directory": {"type": "string", "minLength": 1},
                        "retention_seconds": {"type": "integer", "minimum": 3600},
                    },
                },
                "work": {
                    "type": "object", "required": ["directory"],
                    "properties": {"directory": {"type": "string", "minLength": 1}},
                },
                "results": {
                    "type": "object", "required": ["directory", "retention_seconds"],
                    "properties": {
                        "directory": {"type": "string", "minLength": 1},
                        "retention_seconds": {"type": "integer", "minimum": 3600},
                    },
                },
                "max_retention_seconds": {"type": "integer", "minimum": 3600},
            },
        },
        "processing": {
            "type": "object",
            "required": ["retry", "lease_seconds", "stale_after_seconds"],
            "properties": {
                "retry": _RETRY_POLICY,
                "extraction_retry": _RETRY_POLICY,   # optional: LLM extraction (defaults to "retry")
                "email_retry": _RETRY_POLICY,        # optional: e-mail delivery (defaults to "retry")
                "lease_seconds": {"type": "integer", "minimum": 60},
                "stale_after_seconds": {"type": "integer", "minimum": 30},
            },
        },
        "notifications": {
            "type": "object",
            "required": ["email"],
            "properties": {
                "email": {
                    "type": "object",
                    "properties": {
                        "send_partial_results": {"type": "boolean"},
                        "send_failure_notice": {"type": "boolean"},
                        "attach_pdfs": {"type": "boolean"},
                        "attach_format": {"enum": ["zip", "pdf"]},
                        "max_attachment_total_bytes": {"type": "integer", "minimum": 0},
                        "download_link_ttl_seconds": {"type": "integer", "minimum": 3600},
                        "include_extracted_information": {"type": "boolean"},
                    },
                }
            },
        },
    },
}

STT_YAML_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["stt"],
    "properties": {
        "stt": {
            "type": "object",
            "required": ["engine", "model", "device", "compute_type"],
            "properties": {
                "engine": {"type": "string", "minLength": 1},
                "model": {"type": "string", "minLength": 1},
                "device": {"enum": ["cpu", "cuda", "auto"]},
                "compute_type": {"type": "string"},
                "cpu_threads": {"type": "integer", "minimum": 0},
                "num_workers": _POS_INT,
                "download_root": {"type": ["string", "null"]},
                "language": {"type": ["string", "null"]},
                "task": {"enum": ["transcribe", "translate"]},
                "beam_size": _POS_INT,
                "vad_filter": {"type": "boolean"},
                "vad_min_silence_ms": {"type": "integer", "minimum": 0},
                "condition_on_previous_text": {"type": "boolean"},
                "initial_prompt": {"type": ["string", "null"]},
                "word_timestamps": {"type": "boolean"},
                "chunk_length": {"type": ["integer", "null"], "minimum": 1},
                "preprocessing": {
                    "type": "object",
                    "properties": {
                        "ffmpeg_binary": {"type": "string"},
                        "sample_rate": _POS_INT,
                        "channels": {"enum": [1, 2]},
                        "filters": {"type": ["string", "null"]},
                    },
                },
                "paragraphs": {
                    "type": "object",
                    "properties": {
                        "max_gap_seconds": _NON_NEG_NUM,
                        "max_sentences": _POS_INT,
                    },
                },
            },
        }
    },
}

AI_SETTINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["llm", "ai"],
    "properties": {
        "llm": {
            "type": "object",
            "required": ["provider", "model"],
            "properties": {
                "provider": {"type": "string", "minLength": 1},
                "model": {"type": "string", "minLength": 1},
                "base_url": {"type": "string"},
                "api_key_env": {"type": "string"},
                "temperature": {"type": "number", "minimum": 0, "maximum": 2},
                "max_context_length": _POS_INT,
                "max_output_tokens": _POS_INT,
                "timeout": {"type": "number", "exclusiveMinimum": 0},
                "options": {"type": "object"},
            },
        },
        "ai": {
            "type": "object",
            "required": ["language", "extraction", "retry"],
            "properties": {
                "language": {"type": "string", "minLength": 2},
                "response_format": {"enum": ["json"]},
                "max_transcript_chars": _POS_INT,
                "max_response_chars": _POS_INT,
                "extraction": {
                    "type": "object",
                    "required": ["enabled", "schema", "system_prompt", "user_prompt"],
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "required": {"type": "boolean"},
                        "schema": {"type": "string", "minLength": 1},
                        "system_prompt": {"type": "string", "minLength": 1},
                        "user_prompt": {"type": "string", "minLength": 1},
                        "repair_prompt": {"type": "string", "minLength": 1},
                        "additional_context": {"type": "string"},
                        "placeholder_values": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "retry": {
                    "type": "object",
                    "required": ["max_attempts"],
                    "properties": {"max_attempts": _POS_INT, "delay_seconds": _NON_NEG_NUM},
                },
            },
        },
    },
}

PDF_TEMPLATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["document", "fonts", "sections"],
    "properties": {
        "document": {
            "type": "object",
            "properties": {
                "language": {"enum": ["fa", "en"]},
                "page_size": {"enum": ["A4", "LETTER"]},
                "margins_mm": {
                    "type": "object",
                    "properties": {k: _NON_NEG_NUM for k in ("top", "bottom", "left", "right")},
                },
                "title": _I18N_TEXT,
                "author": {"type": "string"},
                "subject": _I18N_TEXT,
            },
        },
        "fonts": {
            "type": "object",
            "required": ["regular"],
            "properties": {
                "regular": {"type": "string"},
                "bold": {"type": "string"},
                "size": {"type": "number", "minimum": 6},
                "heading_size": {"type": "number", "minimum": 6},
                "title_size": {"type": "number", "minimum": 6},
                "line_spacing": {"type": "number", "minimum": 1},
            },
        },
        "sections": {
            "type": "array",
            "items": {"enum": ["metadata", "extraction", "transcript"]},
            "uniqueItems": True,
        },
        "metadata": {
            "type": "object",
            "properties": {
                "visible": {"type": "boolean"},
                "title": _I18N_TEXT,
                "fields": {
                    "type": "array",
                    "items": {"enum": [
                        "filename", "processing_date", "language", "duration",
                        "stt_model", "llm_model", "job_id",
                    ]},
                },
                "labels": {"type": "object", "additionalProperties": _I18N_TEXT},
            },
        },
        "extraction": {
            "type": "object",
            "properties": {
                "visible": {"type": "boolean"},
                "title": _I18N_TEXT,
                "fields": {"oneOf": [{"const": "*"}, {"type": "array", "items": {"type": "string"}}]},
                "hide_empty": {"type": "boolean"},
                "labels": {"type": "object", "additionalProperties": _I18N_TEXT},
                "unavailable_text": _I18N_TEXT,
            },
        },
        "transcript": {
            "type": "object",
            "properties": {
                "visible": {"type": "boolean"},
                "title": _I18N_TEXT,
                "show_timestamps": {"type": "boolean"},
                "empty_text": _I18N_TEXT,
            },
        },
    },
}


@dataclass(frozen=True)
class RuntimeConfig:
    """Immutable, validated view of every configuration file."""

    config_dir: Path
    app: dict[str, Any]
    stt: dict[str, Any]
    llm: dict[str, Any]
    ai: dict[str, Any]
    extraction_schema: dict[str, Any]
    extraction_schema_name: str
    prompts: dict[str, str]
    pdf: dict[str, Any]
    fingerprint: str
    sources: dict[str, Path] = field(default_factory=dict)

    # ---- convenience accessors -------------------------------------------
    @property
    def uploads(self) -> dict[str, Any]:
        return self.app["uploads"]

    @property
    def storage(self) -> dict[str, Any]:
        return self.app["storage"]

    @property
    def retry_policy(self) -> dict[str, Any]:
        return self.app["processing"]["retry"]

    def retry_for(self, kind: str = "default") -> dict[str, Any]:
        """Retry policy of a stage kind: ``default`` | ``extraction`` | ``email``.

        Slow or restartable external services (local LLM, SMTP) get their own, longer policy so a
        short outage does not permanently fail work whose input is still safely stored.
        """
        processing = self.app["processing"]
        return processing.get(f"{kind}_retry") or processing["retry"]

    @property
    def email(self) -> dict[str, Any]:
        return self.app["notifications"].get("email", {})

    @property
    def extraction(self) -> dict[str, Any]:
        return self.ai["extraction"]

    @property
    def extraction_enabled(self) -> bool:
        return bool(self.extraction.get("enabled", True))

    @property
    def extraction_required(self) -> bool:
        return self.extraction_enabled and bool(self.extraction.get("required", True))

    @property
    def language(self) -> str:
        return self.ai["language"]

    @property
    def language_name(self) -> str:
        return _LANGUAGE_NAMES.get(self.language, self.language)

    def storage_dir(self, kind: str) -> Path:
        """Absolute directory for ``archive`` | ``work`` | ``results``."""
        raw = Path(self.storage[kind]["directory"])
        return raw if raw.is_absolute() else Path(settings.MEDIA_ROOT) / raw

    def backoff_delay(self, attempt: int, kind: str = "default") -> float:
        """Exponential backoff delay (seconds) before retry number ``attempt`` (1-based)."""
        policy = self.retry_for(kind)
        delay = float(policy["initial_delay_seconds"]) * float(policy["backoff_multiplier"]) ** max(attempt - 1, 0)
        return min(delay, float(policy["max_delay_seconds"]))


# --------------------------------------------------------------------------
# Loading helpers
# --------------------------------------------------------------------------
def _read_text(path: Path, what: str) -> str:
    if not path.is_file():
        raise ConfigError(f"{what} not found: {path}. Create the file or fix the path in the configuration.")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"{what} at {path} could not be read as UTF-8: {exc}") from exc


def _load_yaml(path: Path, what: str) -> dict[str, Any]:
    text = _read_text(path, what)
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{what} at {path} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{what} at {path} must contain a YAML mapping at the top level.")
    return data


def _validate_shape(data: dict[str, Any], schema: dict[str, Any], path: Path, what: str) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        details = "; ".join(
            f"{'.'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}" for err in errors[:10]
        )
        raise ConfigError(f"{what} at {path} is invalid: {details}")


def _resolve_in(base: Path, relative: str, what: str) -> Path:
    """Resolve a config-relative path and refuse escapes outside the config directory."""
    candidate = (base / relative).resolve()
    if base.resolve() not in candidate.parents and candidate != base.resolve():
        raise ConfigError(f"{what} path '{relative}' must stay inside {base}.")
    return candidate


def validate_extraction_schema(schema: Any, path: Path | str) -> None:
    if not isinstance(schema, dict):
        raise ConfigError(f"Extraction schema {path} must be a JSON object.")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ConfigError(f"Extraction schema {path} is not a valid JSON Schema: {exc.message}") from exc
    if schema.get("type") != "object" or not isinstance(schema.get("properties"), dict) or not schema["properties"]:
        raise ConfigError(
            f"Extraction schema {path} must describe an object with at least one entry in 'properties'."
        )


def load_config(config_dir: Path | None = None) -> RuntimeConfig:
    """Load and fully validate every configuration file. Raises :class:`ConfigError`."""
    base = Path(config_dir or settings.APP_CONFIG_DIR)
    ai_dir = base / "ai"
    sources: dict[str, Path] = {}

    app_path = base / "app.yaml"
    app_cfg = _load_yaml(app_path, "Application configuration")
    _validate_shape(app_cfg, APP_YAML_SCHEMA, app_path, "Application configuration")
    sources["app"] = app_path

    stt_path = ai_dir / "stt.yaml"
    stt_cfg = _load_yaml(stt_path, "Speech-to-text configuration")
    _validate_shape(stt_cfg, STT_YAML_SCHEMA, stt_path, "Speech-to-text configuration")
    sources["stt"] = stt_path

    ai_path = ai_dir / "settings.yaml"
    ai_cfg = _load_yaml(ai_path, "AI settings")
    _validate_shape(ai_cfg, AI_SETTINGS_SCHEMA, ai_path, "AI settings")
    sources["ai"] = ai_path

    llm = dict(ai_cfg["llm"])
    # Deployment-specific endpoint override (Docker vs local) — not an AI behaviour change.
    if os.environ.get("LLM_BASE_URL"):
        llm["base_url"] = os.environ["LLM_BASE_URL"]
    llm.setdefault("options", {})

    extraction = ai_cfg["ai"]["extraction"]
    schema_path = _resolve_in(ai_dir, extraction["schema"], "Extraction schema")
    schema_text = _read_text(schema_path, "Extraction schema")
    try:
        schema = json.loads(schema_text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Extraction schema {schema_path} is not valid JSON: {exc}") from exc
    validate_extraction_schema(schema, schema_path)
    sources["schema"] = schema_path

    prompts: dict[str, str] = {}
    for key, cfg_key in (("system", "system_prompt"), ("user", "user_prompt"), ("repair", "repair_prompt")):
        if cfg_key not in extraction:
            continue
        p = _resolve_in(ai_dir, extraction[cfg_key], f"Prompt '{cfg_key}'")
        text = _read_text(p, f"Prompt file '{cfg_key}'")
        if not text.strip():
            raise ConfigError(f"Prompt file '{cfg_key}' at {p} is empty.")
        prompts[key] = text
        sources[f"prompt_{key}"] = p
    from apps.information_extraction.services.prompts import PromptTemplateError, check_template, placeholders

    if "transcript" not in placeholders(prompts["user"]):
        raise ConfigError(
            f"User prompt {sources['prompt_user']} must contain the '{{{{ transcript }}}}' placeholder."
        )
    for key, text in prompts.items():
        try:
            check_template(text, str(sources[f"prompt_{key}"]))
        except PromptTemplateError as exc:
            raise ConfigError(str(exc)) from exc

    pdf_path = ai_dir / "pdf_template.yaml"
    pdf_cfg = _load_yaml(pdf_path, "PDF template")
    _validate_shape(pdf_cfg, PDF_TEMPLATE_SCHEMA, pdf_path, "PDF template")
    sources["pdf"] = pdf_path
    for font_key in ("regular", "bold"):
        font = pdf_cfg["fonts"].get(font_key)
        if font and not resolve_project_path(font).is_file():
            raise ConfigError(
                f"PDF font '{font_key}' not found at {resolve_project_path(font)} (configured in {pdf_path}). "
                "Install the Vazirmatn font or point the template to another TTF font with Persian glyphs."
            )
    fields_cfg = pdf_cfg.get("extraction", {}).get("fields", "*")
    if isinstance(fields_cfg, list):
        unknown = [f for f in fields_cfg if f not in schema["properties"]]
        if unknown:
            raise ConfigError(
                f"PDF template {pdf_path} lists extraction fields not present in the active schema: {unknown}."
            )

    _validate_provider(llm, ai_path)

    digest = hashlib.sha256()
    for name in sorted(sources):
        digest.update(name.encode())
        digest.update(sources[name].read_bytes())

    return RuntimeConfig(
        config_dir=base,
        app=app_cfg,
        stt=stt_cfg["stt"],
        llm=llm,
        ai=ai_cfg["ai"],
        extraction_schema=schema,
        extraction_schema_name=str(schema.get("$id") or schema_path.stem),
        prompts=prompts,
        pdf=pdf_cfg,
        fingerprint=digest.hexdigest()[:16],
        sources=sources,
    )


def _validate_provider(llm: dict[str, Any], path: Path) -> None:
    from apps.information_extraction.providers.registry import ProviderNotFound, resolve_provider_class

    try:
        resolve_provider_class(llm["provider"])
    except ProviderNotFound as exc:
        raise ConfigError(f"{exc} (configured as llm.provider in {path}).") from exc


def resolve_project_path(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else Path(settings.BASE_DIR) / p


_lock = threading.Lock()
_cached: RuntimeConfig | None = None


def get_config() -> RuntimeConfig:
    """Return the process-wide validated configuration (loaded once per process)."""
    global _cached
    if _cached is None:
        with _lock:
            if _cached is None:
                _cached = load_config()
    return _cached


def reload_config() -> RuntimeConfig:
    """Drop the cached configuration and reload it (used by tests and restarts)."""
    global _cached
    with _lock:
        _cached = load_config()
    return _cached
