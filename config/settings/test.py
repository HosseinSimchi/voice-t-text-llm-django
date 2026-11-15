import os

os.environ.setdefault("DJANGO_LOAD_ENV_LOCAL", "false")

"""Settings for the automated test-suite (no Redis, SMTP, Whisper or Ollama needed)."""

import tempfile
from pathlib import Path

from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = "test-secret-key-not-for-production-0123456789abcdefghijklmnopqrstuvwxyz"
ALLOWED_HOSTS = ["testserver", "localhost"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
EMAIL_REAL_DELIVERY = True  # locmem stands in for SMTP in the unit tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_BROKER_URL = "memory://"
MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="audio-intel-test-media-"))
SITE_BASE_URL = "http://testserver"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
REST_FRAMEWORK = {**REST_FRAMEWORK}  # noqa: F405
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {"uploads": "1000/hour", "status": "10000/hour", "downloads": "10000/hour"}
LOGGING = {"version": 1, "disable_existing_loggers": False, "root": {"level": "WARNING"}}
STATIC_ROOT = Path(tempfile.mkdtemp(prefix="audio-intel-test-static-"))
CELERY_TASK_EAGER_PROPAGATES = True
