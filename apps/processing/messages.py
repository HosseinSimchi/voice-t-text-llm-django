"""User-facing texts for status values and error codes (Persian and English)."""

from __future__ import annotations

SUCCESS_MESSAGE_FA = (
    "عملیات با موفقیت انجام شد. لطفاً ایمیل خود را بررسی کنید. "
    "فایل‌های خروجی و اطلاعات استخراج‌شده برای شما ارسال شده‌اند."
)
PARTIAL_MESSAGE_FA = (
    "پردازش به‌صورت ناقص انجام شد. بخشی از فایل‌ها با موفقیت پردازش شدند. "
    "لطفاً ایمیل خود را برای مشاهده گزارش نتایج بررسی کنید."
)
NOT_DELIVERED_NOTE_FA = (
    "توجه: ایمیل واقعی ارسال نشد زیرا ارسال ایمیل (SMTP) در این محیط پیکربندی نشده است. "
    "فایل‌های PDF را از همین صفحه دریافت کنید."
)
SUCCESS_NOT_DELIVERED_FA = "پردازش همه فایل‌ها با موفقیت انجام شد. " + NOT_DELIVERED_NOTE_FA
FAILED_MESSAGE_FA = "متأسفانه پردازش هیچ‌یک از فایل‌های صوتی با موفقیت انجام نشد."
EMAIL_FAILED_MESSAGE_FA = (
    "پردازش فایل‌ها انجام شد اما ارسال ایمیل با خطا مواجه شد. "
    "می‌توانید فایل‌های PDF را از همین صفحه دریافت کنید."
)

ERRORS: dict[str, dict[str, str]] = {
    "unsupported_file_type": {"fa": "نوع فایل پشتیبانی نمی‌شود.", "en": "Unsupported file type."},
    "symbolic_link_not_allowed": {"fa": "پیوند نمادین مجاز نیست.", "en": "Symbolic links are not allowed."},
    "encrypted_entry_not_supported": {"fa": "فایل رمزگذاری‌شده پشتیبانی نمی‌شود.",
                                      "en": "Encrypted entries are not supported."},
    "nested_archive_not_supported": {"fa": "آرشیو تودرتو پشتیبانی نمی‌شود.",
                                     "en": "Nested archives are not supported."},
    "file_too_large": {"fa": "حجم فایل بیش از حد مجاز است.", "en": "The file exceeds the size limit."},
    "empty_file": {"fa": "فایل خالی است.", "en": "The file is empty."},
    "too_many_files": {"fa": "تعداد فایل‌ها بیش از حد مجاز است.", "en": "Too many files in the archive."},
    "extraction_size_limit_reached": {"fa": "مجموع حجم استخراج‌شده از حد مجاز گذشت.",
                                      "en": "Total extracted size limit reached."},
    "content_does_not_match_extension": {"fa": "محتوای فایل با پسوند آن مطابقت ندارد.",
                                         "en": "File content does not match its extension."},
    "corrupt_entry": {"fa": "فایل داخل آرشیو خراب است.", "en": "The archive entry is corrupted."},
    "rar_tool_unavailable": {"fa": "ابزار استخراج RAR در سرور در دسترس نیست.",
                             "en": "No RAR extraction tool is available on the server."},
    "malformed_audio": {"fa": "فایل صوتی معیوب است یا قابل رمزگشایی نیست.",
                        "en": "The audio file is malformed or cannot be decoded."},
    "no_audio_stream": {"fa": "فایل حاوی صدا نیست.", "en": "The file contains no audio stream."},
    "empty_audio": {"fa": "فایل صوتی خالی است.", "en": "The audio file is empty."},
    "duration_exceeded": {"fa": "مدت فایل صوتی بیش از حد مجاز است.",
                          "en": "The audio is longer than allowed."},
    "llm_unavailable": {"fa": "سرویس مدل زبانی در دسترس نبود.", "en": "The language model was unavailable."},
    "llm_invalid_output": {"fa": "خروجی مدل زبانی معتبر نبود.",
                           "en": "The language model returned invalid output."},
    "archive_missing": {"fa": "فایل آرشیو دیگر در دسترس نیست.", "en": "The archive is no longer available."},
    "no_file_processed": {"fa": "هیچ فایلی پردازش نشد.", "en": "No file could be processed."},
    "no_supported_audio": {"fa": "فایل صوتی پشتیبانی‌شده‌ای یافت نشد.", "en": "No supported audio file found."},
    "email_delivery_failed": {"fa": "ارسال ایمیل ناموفق بود.", "en": "E-mail delivery failed."},
    "retention_expired": {"fa": "مهلت پردازش به پایان رسید.", "en": "The processing window expired."},
    "internal_error": {"fa": "خطای داخلی رخ داد.", "en": "An internal error occurred."},
}


def error_text(code: str, lang: str = "en", default: str = "") -> str:
    entry = ERRORS.get(code or "")
    if entry:
        return entry.get(lang) or entry["en"]
    return default or (ERRORS["internal_error"][lang] if code else "")
