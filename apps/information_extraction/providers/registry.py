"""Provider registry: built-in names plus dotted-path adapters.

To add a provider without touching the extraction engine, implement
``LLMProvider.complete`` in any importable module and set
``llm.provider: package.module.ClassName`` in ``config/ai/settings.yaml``.
"""

from __future__ import annotations

import importlib
from typing import Any

from .base import LLMProvider

BUILTIN_PROVIDERS = {
    "ollama": "apps.information_extraction.providers.ollama.OllamaProvider",
    "openai_compatible": "apps.information_extraction.providers.openai_compatible.OpenAICompatibleProvider",
}


class ProviderNotFound(Exception):
    pass


def resolve_provider_class(name: str) -> type[LLMProvider]:
    path = BUILTIN_PROVIDERS.get(name, name)
    module_name, _, attr = path.rpartition(".")
    if not module_name:
        raise ProviderNotFound(
            f"Unsupported LLM provider '{name}'. Use one of {sorted(BUILTIN_PROVIDERS)} "
            "or a dotted path to an LLMProvider subclass"
        )
    try:
        cls = getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError) as exc:
        raise ProviderNotFound(f"LLM provider '{name}' could not be imported: {exc}") from exc
    if not (isinstance(cls, type) and issubclass(cls, LLMProvider)):
        raise ProviderNotFound(f"LLM provider '{name}' is not a subclass of LLMProvider")
    return cls


def build_provider(llm_config: dict[str, Any]) -> LLMProvider:
    return resolve_provider_class(llm_config["provider"])(llm_config)
