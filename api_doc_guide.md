# راهنمای API: پلتفرم هوشمند پردازش صوت فارسی

این سند برای **توسعه‌دهنده‌ای** است که می‌خواهد از بیرون (برنامهٔ دیگر، سرویس، اسکریپت) با این پروژه کار کند.
همهٔ مثال‌های پاسخ، خروجی واقعی خود API هستند و نمونه‌کدها اجرا و آزمایش شده‌اند.

---

## فهرست
1. [خلاصهٔ یک‌صفحه‌ای](#1-خلاصهٔ-یکصفحهای)
2. [آدرس‌ها و مستندات تعاملی](#2-آدرسها-و-مستندات-تعاملی)
3. [گردش کار](#3-گردش-کار)
4. [احراز هویت و دسترسی](#4-احراز-هویت-و-دسترسی)
5. [Endpoint ها](#5-endpoint-ها)
6. [وضعیت‌ها](#6-وضعیتها)
7. [خطاها](#7-خطاها)
8. [محدودیت‌ها و Rate limit](#8-محدودیتها-و-rate-limit)
9. [نمونه کد کامل](#9-نمونه-کد-کامل)
10. [Postman / Swagger](#10-postman--swagger)
11. [ایمیل](#11-ایمیل)
12. [نکات مهم برای یکپارچه‌سازی](#12-نکات-مهم-برای-یکپارچهسازی)
13. [عیب‌یابی](#13-عیبیابی)

---

## 1. خلاصهٔ یک‌صفحه‌ای

**کار سیستم:** یک فایل **ZIP یا RAR** شامل چند فایل صوتی (mp3، wav، m4a، aac، ogg، flac، opus) و یک **آدرس ایمیل** می‌گیرد. برای هر فایل صوتی متن فارسی را استخراج می‌کند، یک **PDF** می‌سازد، با مدل زبانی اطلاعات ساختاریافته (خلاصه، تصمیمات، اقدامات و…) استخراج می‌کند و نتیجه را **ایمیل** می‌کند. همین نتایج از API هم قابل دریافت است.

**چهار قدم:**

| قدم | درخواست | نتیجه |
|---|---|---|
| ۱. ارسال | `POST /api/v1/jobs/` (فایل + ایمیل) | `202` + `job_id` + **`access_token`** (فقط یک بار نمایش داده می‌شود!) |
| ۲. پیگیری | `GET /api/v1/jobs/{job_id}/` | `state` و `progress` (هر 10 تا 15 ثانیه بپرسید) |
| ۳. نتایج | `GET /api/v1/jobs/{job_id}/results/` | متن/اطلاعات استخراج‌شده + لینک دانلود هر PDF |
| ۴. دانلود | `GET /api/v1/jobs/{job_id}/download/` | یک **ZIP** با PDF همهٔ فایل‌ها |

**زمان:** پردازش **کند** است (روی CPU حدود ۴ تا ۶ دقیقه برای هر فایل ۲۵ ثانیه‌ای). درخواست ارسال فوراً جواب می‌دهد؛ پردازش در پس‌زمینه انجام می‌شود، پس کلاینت باید **پیگیری (polling)** کند.

---

## 2. آدرس‌ها و مستندات تعاملی

| | آدرس |
|---|---|
| **Base URL** | لوکال: `http://localhost:8000`؛ سرور: آدرسی که مدیر سیستم می‌دهد (مثلاً `https://audio.example.com`) |
| مستندات تعاملی (Swagger UI) | `{BASE}/api/docs/` |
| فایل OpenAPI (YAML) | `{BASE}/api/schema/` |
| فایل OpenAPI (JSON) | `{BASE}/api/schema/?format=json` |
| سلامت سرویس | `GET {BASE}/healthz` ← `{"status": "ok"}` |

همهٔ endpoint های API زیر مسیر **`/api/v1/`** هستند (نسخه‌بندی‌شده).

> اگر سرور روی اینترنت است و مدیر سیستم برای آپلود رمز عبور (Basic Auth) گذاشته، برای `POST /api/v1/jobs/` باید `-u user:password` (در `requests`: `auth=(user, password)`) هم بفرستید. این رمز با `access_token` فرق دارد.

---

## 3. گردش کار

```
کلاینت                         سرور
  │  POST /api/v1/jobs/ (file, email)
  │ ─────────────────────────────▶  اعتبارسنجی آرشیو، ذخیره، ساخت کار
  │ ◀─────────────────────────────  202 {job_id, access_token}
  │
  │  GET /api/v1/jobs/{id}/  (هر ~10 ثانیه)        ┌ پردازش در پس‌زمینه:
  │ ─────────────────────────────▶                  │ باز کردن آرشیو ← تبدیل گفتار به متن
  │ ◀─────────────────────────────  state, progress │ ← PDF ← استخراج اطلاعات ← ایمیل
  │   ... تا state یکی از COMPLETED / PARTIALLY_COMPLETED / FAILED شود
  │
  │  GET /api/v1/jobs/{id}/results/
  │  GET /api/v1/jobs/{id}/download/        (ZIP همهٔ PDF ها)
  │  GET /api/v1/results/{result_id}/download/   (PDF یک فایل)
```

**نکتهٔ مهم:** «پاسخ 202» یعنی فایل **پذیرفته شد**، نه اینکه پردازش تمام شده باشد. نتیجه فقط وقتی نهایی است که `state` پایانی شود.

---

## 4. احراز هویت و دسترسی

سیستم **ثبت‌نام و لاگین ندارد.** دسترسی به هر کار با یک **توکن مخصوص همان کار** است.

* در پاسخ `POST /api/v1/jobs/` فیلد **`access_token`** برگردانده می‌شود. **فقط همان یک بار.** سرور فقط هش آن را نگه می‌دارد و دوباره قابل بازیابی نیست. حتماً ذخیره‌اش کنید.
* در همهٔ درخواست‌های بعدی همان کار یکی از این دو هدر را بفرستید:

```
Authorization: Bearer <access_token>
```
یا
```
X-Job-Token: <access_token>
```

* توکن هر کار فقط به همان کار دسترسی می‌دهد.
* اگر توکن نباشد یا غلط باشد، پاسخ **`404`** است (نه 403)، تا نشود وجود یک کار را حدس زد. پس `404` یعنی «کار وجود ندارد **یا** اجازهٔ دسترسی ندارید».
* **لینک‌های امضاشده:** لینک‌های داخل ایمیل پارامتر `?sig=...` دارند و بدون توکن کار می‌کنند (برای گیرندهٔ ایمیل). اعتبار آن‌ها پیش‌فرض 7 روز است و هر امضا فقط برای همان کار/فایل معتبر است.

---

## 5. Endpoint ها

| Method | مسیر | کار |
|---|---|---|
| `POST` | `/api/v1/jobs/` | ارسال آرشیو و ایمیل، ساخت کار |
| `GET` | `/api/v1/jobs/{job_id}/` | وضعیت و پیشرفت |
| `GET` | `/api/v1/jobs/{job_id}/results/` | نتایج هر فایل (متن، استخراج، لینک PDF) |
| `GET` | `/api/v1/jobs/{job_id}/download/` | **یک ZIP** شامل PDF همهٔ فایل‌های موفق |
| `GET` | `/api/v1/results/{result_id}/download/` | PDF یک فایل |
| `GET` | `/healthz` | سلامت سرویس (بدون احراز هویت) |

### 5.1 ارسال: `POST /api/v1/jobs/`

* **Content-Type:** فقط `multipart/form-data` (بدنهٔ JSON پذیرفته نمی‌شود).
* **فیلدها:**

| فیلد | نوع | توضیح |
|---|---|---|
| `file` | فایل | آرشیو **ZIP یا RAR** (حداکثر 500 مگابایت) |
| `email` | متن | آدرس گیرندهٔ نتیجه |

```bash
curl -X POST http://localhost:8000/api/v1/jobs/ \
  -F "file=@meetings.zip;type=application/zip" \
  --form-string "email=user@example.com"
```

**پاسخ موفق `202 Accepted`:**
```json
{
  "job_id": "5a253050-c61c-4710-aa71-1b134685f190",
  "status": "queued",
  "message": "Your files have been accepted for processing.",
  "access_token": "YKpuoo0RFuRwGAL-KGIIt5iNtbik7nSweHzYfgIZYTA",
  "status_url": "/api/v1/jobs/5a253050-c61c-4710-aa71-1b134685f190/",
  "audio_files": 1,
  "rejected_entries": 1
}
```
* `audio_files`: تعداد فایل صوتی معتبر داخل آرشیو.
* `rejected_entries`: تعداد ورودی‌هایی که **پشتیبانی نمی‌شوند** (مثلاً `notes.txt`)؛ آن‌ها نادیده گرفته می‌شوند و مانع بقیه نیستند. بعداً در `files` با وضعیت `SKIPPED` دیده می‌شوند.
* آرشیو **خراب، ناامن یا بدون فایل صوتی معتبر** رد می‌شود (`400`) و **هیچ کاری ساخته نمی‌شود**.

### 5.2 وضعیت: `GET /api/v1/jobs/{job_id}/`

```json
{
  "job_id": "1a0ad771-33d0-4f28-b196-5aa54cc025de",
  "state": "COMPLETED",
  "current_stage": "DONE",
  "progress": 100,
  "total_audio_files": 1,
  "successful_files": 1,
  "partial_files": 0,
  "failed_files": 0,
  "skipped_files": 1,
  "email_status": "SENT",
  "email_transport": "smtp",
  "retry_count": 0,
  "uploaded_at": "2026-11-15T13:52:06.337241+03:30",
  "archive_retain_until": "2026-11-15T14:52:06.337241+03:30",
  "completed_at": "2026-11-15T13:52:14.560633+03:30",
  "error": null,
  "message": {
    "kind": "success",
    "text": "عملیات با موفقیت انجام شد. لطفاً ایمیل خود را بررسی کنید. فایل‌های خروجی و اطلاعات استخراج‌شده برای شما ارسال شده‌اند."
  },
  "files": [
    {"result_id": "873c2603-06b9-4424-938f-0eb12752ebcf", "index": 0, "filename": "meeting.wav",
     "status": "COMPLETED", "supported": true, "error_code": null, "error_message_fa": null},
    {"result_id": "a0369ce9-ed3a-4f27-95d6-f71d7144e551", "index": 1, "filename": "notes.txt",
     "status": "SKIPPED", "supported": false, "error_code": "unsupported_file_type",
     "error_message_fa": "نوع فایل پشتیبانی نمی‌شود."}
  ]
}
```

| فیلد | معنی |
|---|---|
| `state` | وضعیت کل کار (جدول بخش 6) |
| `current_stage` | مرحلهٔ کار: `ARCHIVE_EXTRACTION` / `FILE_PROCESSING` / `EMAIL_DELIVERY` / `DONE` |
| `progress` | درصد پیشرفت (0 تا 100)؛ `100` فقط وقتی کار پایانی است |
| `total_audio_files` | تعداد فایل‌های صوتی پشتیبانی‌شده |
| `successful_files` / `partial_files` / `failed_files` / `skipped_files` | شمارش‌ها (`partial` = PDF هست ولی استخراج اطلاعات ناموفق بود) |
| `email_status` | `PENDING` / `SENDING` / `RETRYING` / `SENT` / `FAILED` / `NOT_REQUIRED` |
| `email_transport` | `smtp` یعنی واقعاً به سرور SMTP تحویل شد؛ هر مقدار دیگر (مثل `console`) یعنی **ایمیل واقعی ارسال نشده** (حالت توسعه) |
| `retry_count` | تعداد دفعات تلاش مجدد پس از خطای موقت |
| `archive_retain_until` | آرشیو اصلی حداقل تا این زمان نگه‌داری می‌شود |
| `error` | وقتی کار با خطا تمام شود: `{"code", "message", "message_fa"}`، وگرنه `null` |
| `message` | پیام آمادهٔ نمایش به کاربر (فارسی) + `kind`؛ مقدارهای `kind`: `processing`, `success`, `success_local`, `partial`, `failed`, `email_failed` |
| `files[]` | وضعیت هر ورودی آرشیو (`result_id` شناسهٔ همان فایل است) |

> برای نمایش پیام نهایی به کاربر از `message.kind` استفاده کنید. **پیام موفقیت (`success`) فقط بعد از پذیرفته شدن ایمیل توسط SMTP برگردانده می‌شود.**

### 5.3 نتایج: `GET /api/v1/jobs/{job_id}/results/`

```json
{
  "job_id": "1a0ad771-33d0-4f28-b196-5aa54cc025de",
  "state": "COMPLETED",
  "download_all_url": "/api/v1/jobs/1a0ad771-33d0-4f28-b196-5aa54cc025de/download/",
  "results": [
    {
      "result_id": "873c2603-06b9-4424-938f-0eb12752ebcf",
      "index": 0,
      "filename": "meeting.wav",
      "status": "COMPLETED",
      "supported": true,
      "duration_seconds": 1.0,
      "transcription": {"status": "DONE", "language": "fa", "model": "medium", "characters": 123, "segments": 3},
      "pdf": {
        "status": "DONE",
        "includes_extraction": true,
        "size_bytes": 31827,
        "download_url": "/api/v1/results/873c2603-06b9-4424-938f-0eb12752ebcf/download/"
      },
      "extraction": {
        "status": "DONE",
        "schema": "meeting-analysis-v1",
        "model": "qwen2.5:3b",
        "provider": "ollama",
        "data": {"main_topic": "...", "executive_summary": "...", "key_points": ["..."]}
      },
      "error": null
    }
  ]
}
```

* `download_all_url`: لینک ZIP همهٔ PDF ها؛ وقتی هنوز هیچ PDF ای نیست `null` است.
* `pdf.download_url`: وقتی PDF آماده نیست یا حذف شده `null` است.
* `transcription.status` و `extraction.status`: `PENDING` / `DONE` / `FAILED` / `SKIPPED`.
* **`extraction.data` کاملاً به schema فعال بستگی دارد.** فیلدهای پیش‌فرض (تحلیل جلسه): `main_topic`, `executive_summary`, `key_points`, `decisions`, `action_items` (آرایه‌ای از `{task, owner, due}`), `responsible_people`, `important_dates`, `deadlines`, `organizations_and_people`, `locations`, `important_numbers`, `risks_and_issues`, `follow_up_requirements`. مدیر سیستم می‌تواند schema را عوض کند (مثلاً برای تماس فروش)، پس **کلید‌ها را در کد ثابت فرض نکنید**؛ نام schema فعال در `extraction.schema` است.
* متن کامل رونویسی در این endpoint **برگردانده نمی‌شود** (فقط آمار آن)؛ متن کامل در PDF است.
* اگر استخراج اطلاعات ناموفق باشد، `extraction.data` برابر `null` است ولی PDF رونویسی موجود است.

### 5.4 دانلود PDF یک فایل: `GET /api/v1/results/{result_id}/download/`
پاسخ: `200`، `Content-Type: application/pdf`، `Content-Disposition: attachment; filename="meeting.pdf"`. پاسخ **باینری** است.
```bash
curl -H "Authorization: Bearer $TOKEN" -o meeting.pdf \
  http://localhost:8000/api/v1/results/$RESULT_ID/download/
```

### 5.5 دانلود همهٔ PDF ها: `GET /api/v1/jobs/{job_id}/download/`
یک فایل ZIP (`Content-Type: application/zip`، نام `results-<8 رقم اول شناسه>.zip`) شامل PDF هر فایل موفق با نام `001-نامفایل.pdf`، `002-…`. فایل‌های ناموفق در ZIP نیستند.
```bash
curl -H "Authorization: Bearer $TOKEN" -o results.zip \
  http://localhost:8000/api/v1/jobs/$JOB_ID/download/
```
اگر هنوز هیچ PDF ای آماده نباشد `404`؛ اگر مهلت نگه‌داری نتایج گذشته باشد `410` می‌دهد.

---

## 6. وضعیت‌ها

**وضعیت کار (`state`):**

| مقدار | معنی | پایانی؟ |
|---|---|---|
| `QUEUED` | در صف | خیر |
| `EXTRACTING` | در حال باز کردن آرشیو | خیر |
| `TRANSCRIBING` | تبدیل گفتار به متن | خیر |
| `GENERATING_PDF` | ساخت PDF | خیر |
| `EXTRACTING_INFORMATION` | استخراج اطلاعات با مدل زبانی | خیر |
| `SENDING_EMAIL` | ارسال ایمیل | خیر |
| `RETRYING` | خطای موقت؛ تلاش مجدد خودکار در راه است | خیر |
| `COMPLETED` | همهٔ فایل‌ها کامل پردازش شدند **و** ایمیل پذیرفته شد | **بله** |
| `PARTIALLY_COMPLETED` | بعضی فایل‌ها موفق، بعضی ناموفق (یا استخراج ناموفق) | **بله** |
| `FAILED` | هیچ فایلی پردازش نشد، یا ارسال ایمیل قطعاً ناموفق بود (`error.code = email_delivery_failed`؛ PDF ها قابل دانلودند) | **بله** |

**وضعیت هر فایل (`files[].status`):** `PENDING`, `PREPROCESSING`, `TRANSCRIBING`, `GENERATING_PDF`, `EXTRACTING_INFORMATION`, `RETRYING`, `COMPLETED`, `PARTIALLY_COMPLETED` (PDF رونویسی هست، استخراج اطلاعات نه), `FAILED`, `SKIPPED` (فایل پشتیبانی‌نشده).

**قاعدهٔ پیگیری:** تا وقتی `state` در `COMPLETED` / `PARTIALLY_COMPLETED` / `FAILED` نیست، دوباره بپرسید. `RETRYING` پایان نیست.
همچنین فایل‌های تمام‌شده را می‌توانید پیش از پایان کل کار از `/results/` بگیرید.

---

## 7. خطاها

همهٔ خطاها یک قالب ثابت دارند:
```json
{"error": {"code": "validation_error", "message": "The request is invalid.", "details": {"email": ["پست الکترونیکی صحیح وارد کنید."]}}}
```
`code` را برای منطق برنامه استفاده کنید (پایدار است)؛ `message` برای نمایش به انسان است (ممکن است فارسی یا انگلیسی باشد).

**کدهای HTTP:**

| کد | معنی |
|---|---|
| `202` | آرشیو پذیرفته شد |
| `400` | ورودی نامعتبر (جدول زیر) |
| `404` | کار/فایل وجود ندارد، **یا** توکن/امضا نادرست است؛ یا هنوز PDF ای نیست |
| `410` | مهلت نگه‌داری نتایج (پیش‌فرض 7 روز) تمام شده و حذف شده‌اند |
| `429` | تعداد درخواست‌ها زیاد است؛ هدر `Retry-After` (ثانیه) را رعایت کنید؛ `code = throttled` |
| `500` | خطای داخلی سرور |

**کدهای خطای آپلود (`400`)** (پاسخ‌های واقعی):

| `error.code` | معنی |
|---|---|
| `validation_error` | فیلد `file` یا `email` ناقص/نامعتبر؛ جزئیات در `details` |
| `unsupported_archive_type` | پسوند فایل ZIP یا RAR نیست |
| `invalid_archive_format` | محتوای فایل با ZIP/RAR بودن نمی‌خواند (پسوند جعلی) |
| `invalid_mime_type` | نوع MIME با آرشیو نمی‌خواند |
| `archive_too_large` | حجم آرشیو بیش از حد مجاز (500 مگابایت) |
| `empty_upload` / `empty_archive` | فایل یا آرشیو خالی است |
| `corrupt_archive` | آرشیو خراب است |
| `encrypted_archive` | آرشیو رمزدار است (پشتیبانی نمی‌شود) |
| `archive_path_traversal` | مسیر ناامن (`..` یا مسیر مطلق) داخل آرشیو |
| `archive_compression_ratio` | نسبت فشرده‌سازی مشکوک (بمب فشرده‌سازی) |
| `too_many_entries` / `too_many_files` | تعداد ورودی/فایل صوتی بیش از حد |
| `extracted_too_large` | مجموع حجم استخراج‌شده بیش از حد |
| `no_supported_audio` | هیچ فایل صوتی پشتیبانی‌شده‌ای داخل آرشیو نیست |

کد خطای فایل‌های داخل آرشیو (در `files[].error_code`): `unsupported_file_type`, `nested_archive_not_supported`, `symbolic_link_not_allowed`, `encrypted_entry_not_supported`, `file_too_large`, `empty_file`, `content_does_not_match_extension`, `corrupt_entry`, `malformed_audio`, `no_audio_stream`, `duration_exceeded`, `llm_unavailable`, `llm_invalid_output` و…

> خطای **404** با `code: "error"` برمی‌گردد و پیام فارسی «یافت نشد.» دارد. پیام‌های اعتبارسنجی فیلدها (`details`) فارسی‌اند.

---

## 8. محدودیت‌ها و Rate limit

**محدودیت‌های آرشیو** (قابل تغییر توسط مدیر در `config/app.yaml`):

| مورد | مقدار پیش‌فرض |
|---|---|
| حجم آرشیو | 500 مگابایت |
| تعداد فایل صوتی در هر آرشیو | 100 |
| تعداد کل ورودی‌ها | 500 |
| حجم هر فایل / مجموع استخراج | 500 مگابایت / 2 گیگابایت |
| طول هر فایل صوتی | 3 ساعت |
| فرمت‌های صوتی | mp3, wav, m4a, aac, ogg, flac, opus |
| فرمت آرشیو | zip, rar (آرشیو تودرتو، رمزدار و symlink پشتیبانی نمی‌شود) |

**Rate limit** (به‌ازای هر آدرس IP؛ قابل تغییر با متغیرهای `THROTTLE_*`):

| عملیات | حد پیش‌فرض |
|---|---|
| ارسال آرشیو (`POST /jobs/`) | 20 در ساعت |
| وضعیت و نتایج | 600 در ساعت (یعنی حدود **یک درخواست در هر 6 ثانیه**) |
| دانلودها | 300 در ساعت |

پس **هر 10 تا 15 ثانیه** وضعیت را بپرسید، نه سریع‌تر. اگر چند کاربر پشت یک IP هستند (NAT) سهمیه مشترک است. در پاسخ `429` مقدار `Retry-After` را صبر کنید.

**نگه‌داری داده:**

| داده | مدت |
|---|---|
| آرشیو اصلی | حداقل 1 ساعت و تا پایان پردازش (برای تلاش مجدد خودکار)؛ بعد حذف می‌شود |
| فایل‌های موقت پردازش | بعد از پایان کار حذف می‌شوند |
| PDF ها و نتایج | 7 روز؛ بعد از آن دانلودها `410` می‌دهند |

---

## 9. نمونه کد کامل

### 9.1 Python (با `requests`)
```python
import os
import time

import requests

BASE = "http://localhost:8000"          # آدرس سرور
TERMINAL = {"COMPLETED", "PARTIALLY_COMPLETED", "FAILED"}


class ApiError(Exception):
    def __init__(self, status, error):
        super().__init__(f"HTTP {status}: {error}")
        self.status, self.error = status, error


def _check(resp, ok=(200, 202)):
    if resp.status_code in ok:
        return resp
    try:
        error = resp.json()["error"]
    except Exception:
        error = {"code": "http_error", "message": resp.text[:200]}
    raise ApiError(resp.status_code, error)


def get(url, token, **kw):
    """GET با رعایت Retry-After هنگام 429."""
    while True:
        resp = requests.get(BASE + url, headers={"Authorization": f"Bearer {token}"}, timeout=60, **kw)
        if resp.status_code == 429:
            time.sleep(int(resp.headers.get("Retry-After", "10")))
            continue
        return resp


def upload(path, email):
    with open(path, "rb") as f:
        resp = requests.post(
            f"{BASE}/api/v1/jobs/",
            files={"file": (os.path.basename(path), f, "application/zip")},
            data={"email": email},
            timeout=600,                 # آپلود فایل بزرگ ممکن است طول بکشد
        )
    return _check(resp, ok=(202,)).json()   # شامل job_id و access_token؛ توکن را ذخیره کنید!


def wait_until_done(job_id, token, every=10, timeout=3600):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = _check(get(f"/api/v1/jobs/{job_id}/", token)).json()
        print(f"{status['state']:<24} {status['progress']:>3}%")
        if status["state"] in TERMINAL:
            return status
        time.sleep(every)
    raise TimeoutError("پردازش در مهلت تعیین‌شده تمام نشد")


if __name__ == "__main__":
    job = upload("samples/sample-meeting.zip", "user@example.com")
    job_id, token = job["job_id"], job["access_token"]
    status = wait_until_done(job_id, token)
    print(status["message"]["kind"], "|", status["message"]["text"])

    results = _check(get(f"/api/v1/jobs/{job_id}/results/", token)).json()
    for r in results["results"]:
        if r["supported"]:
            print(r["filename"], r["status"], "| استخراج:", r["extraction"]["status"])

    if results["download_all_url"]:                    # ZIP همهٔ PDF ها
        zip_resp = _check(get(results["download_all_url"], token))
        with open("results.zip", "wb") as out:
            out.write(zip_resp.content)
        print("results.zip ذخیره شد")
```

### 9.2 JavaScript (Node.js 18+ یا مرورگر)
```javascript
const BASE = "http://localhost:8000";
const TERMINAL = ["COMPLETED", "PARTIALLY_COMPLETED", "FAILED"];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(path, token, options = {}) {
  for (;;) {
    const res = await fetch(BASE + path, {
      ...options,
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) },
    });
    if (res.status === 429) { await sleep(Number(res.headers.get("Retry-After") || 10) * 1000); continue; }
    return res;
  }
}

async function upload(fileBlob, filename, email) {
  const form = new FormData();                       // Content-Type را خودکار تنظیم می‌کند
  form.append("file", fileBlob, filename);
  form.append("email", email);
  const res = await api("/api/v1/jobs/", null, { method: "POST", body: form });
  const body = await res.json();
  if (res.status !== 202) throw new Error(`${res.status} ${body.error.code}: ${body.error.message}`);
  return body;                                       // { job_id, access_token, ... }
}

async function waitUntilDone(jobId, token, everyMs = 10000) {
  for (;;) {
    const res = await api(`/api/v1/jobs/${jobId}/`, token);
    if (!res.ok) throw new Error(`status ${res.status}`);
    const s = await res.json();
    console.log(s.state, s.progress + "%");
    if (TERMINAL.includes(s.state)) return s;
    await sleep(everyMs);
  }
}

// استفادهٔ نمونه (Node.js)
import { readFileSync, writeFileSync } from "node:fs";
const { job_id, access_token } = await upload(new Blob([readFileSync("samples/sample-meeting.zip")]),
                                              "sample-meeting.zip", "user@example.com");
const status = await waitUntilDone(job_id, access_token);
console.log(status.message.kind, status.message.text);
const results = await (await api(`/api/v1/jobs/${job_id}/results/`, access_token)).json();
if (results.download_all_url) {
  const zip = await api(results.download_all_url, access_token);
  writeFileSync("results.zip", Buffer.from(await zip.arrayBuffer()));
}
```
(فایل را با پسوند `.mjs` ذخیره کنید یا `"type": "module"` بگذارید.)

### 9.3 فقط با curl (Bash)
```bash
BASE=http://localhost:8000
RESP=$(curl -s -X POST $BASE/api/v1/jobs/ -F "file=@samples/sample-meeting.zip;type=application/zip" --form-string "email=user@example.com")
echo "$RESP"                                           # job_id و access_token را بردارید
JOB_ID=<job_id>; TOKEN=<access_token>

curl -s -H "Authorization: Bearer $TOKEN" $BASE/api/v1/jobs/$JOB_ID/            # تکرار تا state پایانی شود
curl -s -H "Authorization: Bearer $TOKEN" $BASE/api/v1/jobs/$JOB_ID/results/
curl -s -H "Authorization: Bearer $TOKEN" -o results.zip $BASE/api/v1/jobs/$JOB_ID/download/
```
در PowerShell به‌جای `curl` از `curl.exe` استفاده کنید (چون `curl` یک alias دیگر است).

---

## 10. Postman / Swagger

* **Swagger UI:** `{BASE}/api/docs/` را در مرورگر باز کنید. هر endpoint را با دکمهٔ Try it out امتحان کنید. برای endpoint های کار، توکن را در هدر `Authorization` با مقدار `Bearer <token>` بدهید.
* **Postman / Insomnia:** `Import` ← Link ← `{BASE}/api/schema/?format=json`. مجموعهٔ کامل ساخته می‌شود. برای آپلود: Body ← form-data ← کلید `file` (نوع File) و `email` (نوع Text).
* **تولید کلاینت خودکار:** از فایل OpenAPI می‌توانید با ابزارهایی مثل `openapi-generator` برای زبان دلخواه کلاینت بسازید.

---

## 11. ایمیل

کاربر علاوه بر API، نتیجه را **ایمیل** هم می‌گیرد: خلاصهٔ کار، اطلاعات استخراج‌شدهٔ هر فایل و **یک ZIP با PDF همهٔ فایل‌ها**. اگر حجم ZIP بیش از 15 مگابایت باشد به‌جای پیوست، لینک امضاشدهٔ دانلود (اعتبار 7 روز) در ایمیل می‌آید.

* آدرس گیرنده همان `email` ارسال‌شده در `POST /jobs/` است.
* فرستندهٔ ایمیل، یک حساب SMTP است که **مدیر سیستم** یک بار تنظیم می‌کند؛ کلاینت API به آن کاری ندارد.
* «ایمیل ارسال شد» یعنی سرور SMTP پیام را **پذیرفت**؛ تضمین نمی‌کند به صندوق ورودی (و نه اسپم) رسیده باشد.
* خطای موقت ایمیل خودکار تا حدود 15 دقیقه دوباره تلاش می‌شود. اگر نهایتاً ناموفق شود، `state` برابر `FAILED` و `error.code` برابر `email_delivery_failed` است، **ولی PDF ها از API قابل دانلودند.**
* اگر `email_transport` غیر از `smtp` باشد، ایمیل واقعی ارسال نشده (سرور در حالت توسعه است) و `message.kind` برابر `success_local` می‌شود.

---

## 12. نکات مهم برای یکپارچه‌سازی

1. **توکن را فوراً ذخیره کنید** (فقط یک بار برمی‌گردد) و آن را در لاگ یا URL ننویسید.
2. **از HTTPS استفاده کنید** (روی سرور اینترنتی). توکن در هدر ارسال می‌شود و بدون HTTPS قابل شنود است.
3. **پیگیری را با فاصلهٔ 10 تا 15 ثانیه انجام دهید** و `429` را مدیریت کنید.
4. **مهلت (timeout) مناسب بگذارید:** آپلود تا چند دقیقه؛ کل پردازش ممکن است ده‌ها دقیقه طول بکشد (چند فایل، CPU ضعیف).
5. **`PARTIALLY_COMPLETED` و `FAILED` را هم پردازش کنید:** در حالت ناقص PDF فایل‌های موفق قابل دریافت است.
6. **کلیدهای `extraction.data` را ثابت فرض نکنید** (به schema بستگی دارد؛ بخش 5.3).
7. **دقت رونویسی کامل نیست.** تبدیل گفتار فارسی خطا دارد (روی نمونه‌های آزمایشی حدود 30٪ خطای کلمه). اطلاعات استخراج‌شده توسط مدل زبانی کوچک هم ممکن است ناقص یا نادرست باشد؛ برای تصمیم‌های مهم بازبینی انسانی لازم است.
8. **CORS پیکربندی نشده.** فراخوانی مستقیم از JavaScript مرورگرِ یک دامنهٔ دیگر مسدود می‌شود. از سمت سرور (backend-to-backend) فراخوانی کنید، یا از مدیر سیستم بخواهید CORS را برای دامنهٔ شما اضافه کند.
9. **هر پردازش سنگین است** (چند دقیقه CPU). فایل‌های زیاد و بزرگ را پشت‌سرهم و کنترل‌شده بفرستید، نه همزمان.
10. **داده‌ها خصوصی‌اند:** هر توکن فقط به یک کار دسترسی دارد؛ شناسهٔ کار به‌تنهایی دسترسی نمی‌دهد.

---

## 13. عیب‌یابی

| نشانه | علت و راه‌حل |
|---|---|
| `404` روی کاری که تازه ساخته‌اید | توکن را نفرستاده‌اید یا غلط است (هدر `Authorization: Bearer ...`)، یا شناسه را اشتباه کپی کرده‌اید. |
| `400 invalid_archive_format` | فایل واقعاً ZIP/RAR نیست (فقط پسوند عوض شده) یا خراب است. |
| `400 no_supported_audio` | داخل آرشیو هیچ فایل صوتی معتبر نیست؛ فرمت‌ها را بررسی کنید. |
| `400 validation_error` | `file` یا `email` ارسال نشده؛ بدنه باید `multipart/form-data` باشد، نه JSON. |
| `429` | سریع‌تر از حد مجاز می‌پرسید؛ `Retry-After` را صبر کنید و فاصلهٔ polling را زیاد کنید. |
| `state` مدت طولانی `QUEUED` است | سرویس پردازش (worker) روشن نیست؛ به مدیر سیستم خبر بدهید. |
| `state = RETRYING` | خطای موقت (مدل زبانی یا ایمیل)؛ خودکار دوباره تلاش می‌شود، منتظر بمانید. |
| `PARTIALLY_COMPLETED` با `extraction.status = FAILED` | مدل زبانی در دسترس نبود؛ PDF رونویسی هست. مدیر می‌تواند با `manage.py reprocess_job` دوباره اجرا کند. |
| `410` روی دانلود | مهلت 7 روزهٔ نتایج گذشته؛ فایل را دوباره ارسال کنید. |
| ایمیل نرسید ولی `state = COMPLETED` | `email_transport` را ببینید؛ اگر `smtp` است، پوشهٔ اسپم را چک کنید؛ در غیر این صورت SMTP روی سرور تنظیم نشده. |
| `CORS` در کنسول مرورگر | بند 8 بخش 12. |

**برای مدیر سیستم:** راه‌اندازی، تنظیم ایمیل و تنظیمات AI در `GUIDE.md` و `README.md` است.

---

## چک‌لیست تحویل به توسعه‌دهنده

مدیر سیستم این موارد را به او بدهد:

- [ ] **Base URL** (آدرس سرور)
- [ ] اگر آپلود رمز دارد: **نام کاربری و رمز Basic Auth** (غیر از توکن کار)
- [ ] این فایل (`api_doc_guide.md`) و آدرس `/api/docs/`
- [ ] **یک ZIP نمونه** (`samples/sample-meeting.zip`) برای تست
- [ ] توضیح اینکه فرستندهٔ ایمیل کیست و ایمیل واقعی روی سرور فعال است
- [ ] سقف‌های فعلی (حجم، تعداد فایل، rate limit) اگر عوض شده‌اند
