import json

from django.core.management.base import BaseCommand, CommandError

from apps.core.config import ConfigError, load_config


class Command(BaseCommand):
    help = "Validate every YAML/JSON/prompt configuration file and print the active AI setup."

    def handle(self, *args, **options):
        try:
            cfg = load_config()
        except ConfigError as exc:
            raise CommandError(str(exc)) from exc
        summary = {
            "config_dir": str(cfg.config_dir),
            "llm_provider": cfg.llm["provider"],
            "llm_model": cfg.llm["model"],
            "llm_base_url": cfg.llm.get("base_url"),
            "extraction_enabled": cfg.extraction_enabled,
            "extraction_schema": cfg.extraction_schema_name,
            "extraction_fields": list(cfg.extraction_schema["properties"]),
            "stt_model": cfg.stt["model"],
            "stt_device": cfg.stt["device"],
            "fingerprint": cfg.fingerprint,
        }
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
        self.stdout.write(self.style.SUCCESS("Configuration is valid."))
