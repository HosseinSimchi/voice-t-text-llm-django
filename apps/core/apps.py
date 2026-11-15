import logging

from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"

    def ready(self) -> None:
        from . import checks  # noqa: F401  (registers system checks)

        if getattr(settings, "VALIDATE_APP_CONFIG_ON_STARTUP", True):
            from .config import get_config

            cfg = get_config()  # raises ConfigError with an actionable message
            logger.info(
                "Configuration loaded: provider=%s model=%s schema=%s stt=%s fingerprint=%s",
                cfg.llm["provider"], cfg.llm["model"], cfg.extraction_schema_name,
                cfg.stt["model"], cfg.fingerprint,
            )
