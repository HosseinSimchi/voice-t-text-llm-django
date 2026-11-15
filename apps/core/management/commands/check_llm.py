from django.core.management.base import BaseCommand, CommandError

from apps.core.config import get_config
from apps.information_extraction.providers.registry import build_provider


class Command(BaseCommand):
    help = "Check that the configured LLM service is reachable and the configured model is available."

    def handle(self, *args, **options):
        cfg = get_config()
        ok, message = build_provider(cfg.llm).healthcheck()
        self.stdout.write(f"provider={cfg.llm['provider']} model={cfg.llm['model']}")
        if not ok:
            raise CommandError(message)
        self.stdout.write(self.style.SUCCESS(message))
