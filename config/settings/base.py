"""Base Django settings shared by every environment.

All secrets and deployment-specific values come from environment variables.
AI / pipeline behaviour comes from the YAML files under ``config/`` and is
loaded by :mod:`apps.core.config` (never from this module).
"""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _load_env_local() -> None:
    """Load KEY=VALUE pairs from `.env.local` (git-ignored) for local runs; the real environment wins.

    Docker uses its own `.env` through `env_file`, so that file is deliberately not read here.
    """
    path = BASE_DIR / ".env.local"
    if os.environ.get("DJANGO_LOAD_ENV_LOCAL", "true").lower() in {"0", "false", "no"} or not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_local()


def env_str(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise ImproperlyConfigured(f"Environment variable {name} is required.")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ImproperlyConfigured(f"Environment variable {name} must be an integer.") from exc


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = env_str("DJANGO_SECRET_KEY", "")
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

# Public base URL used to build absolute links in emails (e.g. https://audio.example.com).
SITE_BASE_URL = env_str("SITE_BASE_URL", "http://localhost:8000").rstrip("/")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "apps.core",
    "apps.uploads",
    "apps.transcription",
    "apps.document_generation",
    "apps.information_extraction",
    "apps.processing",
    "apps.notifications",
    "apps.web",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database -------------------------------------------------------------
DB_ENGINE = env_str("DB_ENGINE", "sqlite").lower()
if DB_ENGINE == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env_str("POSTGRES_DB", "audio_intelligence"),
            "USER": env_str("POSTGRES_USER", "audio"),
            "PASSWORD": env_str("POSTGRES_PASSWORD", ""),
            "HOST": env_str("POSTGRES_HOST", "localhost"),
            "PORT": env_str("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": env_int("POSTGRES_CONN_MAX_AGE", 60),
        }
    }
elif DB_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": env_str("SQLITE_PATH", str(BASE_DIR / "db.sqlite3")),
            "OPTIONS": {"timeout": 30},
        }
    }
else:
    raise ImproperlyConfigured("DB_ENGINE must be 'sqlite' or 'postgres'.")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Cache (used by DRF throttling) ---------------------------------------
REDIS_URL = env_str("REDIS_URL", "redis://localhost:6379/0")
CACHE_URL = os.environ.get("CACHE_REDIS_URL", "")
if CACHE_URL:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": CACHE_URL}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# --- I18N -----------------------------------------------------------------
LANGUAGE_CODE = "fa"
TIME_ZONE = env_str("TIME_ZONE", "Asia/Tehran")
USE_I18N = True
USE_TZ = True

# --- Static & media -------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
# Media is NEVER served by URL; PDFs are streamed through authorised views only.
MEDIA_ROOT = Path(env_str("MEDIA_ROOT", str(BASE_DIR / "media")))

# Path to the configuration directory holding app.yaml and ai/*.
APP_CONFIG_DIR = Path(env_str("APP_CONFIG_DIR", str(BASE_DIR / "config")))

# --- Upload limits at the HTTP layer --------------------------------------
# Files larger than this are streamed to a temp file instead of memory.
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o640
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o750

# --- Sessions / CSRF ------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 7 * 24 * 3600
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# --- DRF ------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "uploads": env_str("THROTTLE_UPLOADS", "20/hour"),
        "status": env_str("THROTTLE_STATUS", "600/hour"),
        "downloads": env_str("THROTTLE_DOWNLOADS", "300/hour"),
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "UNAUTHENTICATED_USER": None,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Persian Audio Intelligence Platform API",
    "DESCRIPTION": (
        "Upload ZIP/RAR archives of audio files, track processing, and download per-file "
        "Persian PDF transcripts. Job endpoints require the job access token returned at "
        "upload time, sent as `Authorization: Bearer <token>` or `X-Job-Token`."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# --- Celery ---------------------------------------------------------------
CELERY_BROKER_URL = env_str("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = None  # Job state lives in the database, never in Celery results.
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": env_int("CELERY_VISIBILITY_TIMEOUT", 7200)}
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# Local development without Redis: a kombu filesystem broker (single machine only, never production).
_FS_BROKER = os.environ.get("CELERY_FILESYSTEM_BROKER_DIR", "")
if _FS_BROKER:
    Path(_FS_BROKER, "queue").mkdir(parents=True, exist_ok=True)
    Path(_FS_BROKER, "processed").mkdir(parents=True, exist_ok=True)
    CELERY_BROKER_URL = "filesystem://"
    CELERY_BROKER_TRANSPORT_OPTIONS = {
        "data_folder_in": str(Path(_FS_BROKER, "queue")),
        "data_folder_out": str(Path(_FS_BROKER, "queue")),
        "processed_folder": str(Path(_FS_BROKER, "processed")),
        "control_folder": str(Path(_FS_BROKER, "control")),
        "store_processed": False,
    }
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_BEAT_SCHEDULE = {
    "recover-interrupted-jobs": {
        "task": "processing.recover_jobs",
        "schedule": float(env_int("RECOVERY_INTERVAL_SECONDS", 120)),
    },
    "cleanup-expired-storage": {
        "task": "processing.cleanup_storage",
        "schedule": float(env_int("CLEANUP_INTERVAL_SECONDS", 600)),
    },
}

# --- Email (SMTP entirely from environment) -------------------------------
EMAIL_BACKEND = env_str("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env_str("EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env_str("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env_str("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 30)
# True only when messages really leave the machine through SMTP (console/file/memory backends do not).
EMAIL_REAL_DELIVERY = EMAIL_BACKEND.endswith(".smtp.EmailBackend")
DEFAULT_FROM_EMAIL = env_str("DEFAULT_FROM_EMAIL", "Audio Intelligence <no-reply@localhost>")

# --- Logging --------------------------------------------------------------
LOG_DIR = Path(env_str("LOG_DIR", str(BASE_DIR / "logs")))
LOG_LEVEL = env_str("LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"redact": {"()": "apps.core.logging.RedactingFilter"}},
    "formatters": {
        "standard": {"format": "%(asctime)s %(levelname)s %(name)s [%(process)d] %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard", "filters": ["redact"]},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.request": {"level": "WARNING"},
        "faster_whisper": {"level": "WARNING"},
    },
}
if env_bool("LOG_TO_FILE", True):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOGGING["handlers"]["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(LOG_DIR / "app.log"),
        "maxBytes": 10 * 1024 * 1024,
        "backupCount": 5,
        "formatter": "standard",
        "filters": ["redact"],
        "encoding": "utf-8",
    }
    LOGGING["root"]["handlers"].append("file")

# Validate YAML/JSON/prompt configuration at startup (disable only in tooling).
VALIDATE_APP_CONFIG_ON_STARTUP = env_bool("VALIDATE_APP_CONFIG_ON_STARTUP", True)
