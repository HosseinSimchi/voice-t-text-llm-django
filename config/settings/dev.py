"""Local development settings."""

from .base import *  # noqa: F401,F403
from .base import env_str

DEBUG = True
SECRET_KEY = env_str("DJANGO_SECRET_KEY", "") or "dev-insecure-key-change-me-0123456789abcdefghijklmnop"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
EMAIL_BACKEND = env_str("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_REAL_DELIVERY = EMAIL_BACKEND.endswith(".smtp.EmailBackend")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
