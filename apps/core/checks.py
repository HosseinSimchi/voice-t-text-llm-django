"""`manage.py check` integration for configuration and system dependencies."""

import shutil

from django.core.checks import Error, Warning, register

from .config import ConfigError, load_config


@register()
def config_check(app_configs, **kwargs):
    try:
        cfg = load_config()
    except ConfigError as exc:
        return [Error(str(exc), id="audio.E001")]
    warnings = []
    from django.conf import settings

    if not getattr(settings, "EMAIL_REAL_DELIVERY", False):
        warnings.append(Warning(
            f"EMAIL_BACKEND is {settings.EMAIL_BACKEND}: result e-mails are NOT delivered to recipients. "
            "Set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend and the EMAIL_* variables.",
            id="audio.W003"))
    ffmpeg = cfg.stt.get("preprocessing", {}).get("ffmpeg_binary", "ffmpeg")
    if not shutil.which(ffmpeg):
        warnings.append(Warning(
            f"FFmpeg binary '{ffmpeg}' not found; audio normalisation falls back to PyAV.", id="audio.W001"))
    if "rar" in cfg.uploads["allowed_archive_extensions"]:
        from apps.uploads.archives import detect_rar_tool

        if detect_rar_tool(cfg.uploads.get("rar_tool", "auto")) is None:
            warnings.append(Warning(
                "No RAR extraction tool (unrar/7z/bsdtar/unar) found; only stored (uncompressed) RAR "
                "entries can be extracted.", id="audio.W002"))
    return warnings
