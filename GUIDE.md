# راهنمای کامل راه‌اندازی از صفر: اجرای لوکال و روی سرور ابری

این راهنما برای کسی نوشته شده که پروژه را قبلاً ندیده است. دو مسیر دارد:

* **بخش ۲: اجرای لوکال** روی ویندوز (این مسیر اجرا و آزمایش شده است).
* **بخش ۳: اجرای روی سرور ابری** با Docker و HTTPS (فایل‌های لازم نوشته شده‌اند، **اما این مسیر هنوز روی یک سرور واقعی ساخته و آزمایش نشده است**؛ به بخش ۸ نگاه کنید).

---

## فهرست
1. [پروژه چیست و چگونه کار می‌کند](#1-پروژه-چیست-و-چگونه-کار-می‌کند)
2. [اجرای لوکال (ویندوز)](#2-اجرای-لوکال-ویندوز)
3. [اجرا روی سرور ابری](#3-اجرا-روی-سرور-ابری)
4. [تنظیم ایمیل](#4-تنظیم-ایمیل)
5. [تغییر مدل، فیلدهای استخراج، پرامپت و PDF](#5-تغییر-مدل-فیلدهای-استخراج-پرامپت-و-pdf)
6. [آزمایش و راستی‌آزمایی](#6-آزمایش-و-راستی‌آزمایی)
7. [عیب‌یابی](#7-عیب‌یابی)
8. [محدودیت‌های شناخته‌شده](#8-محدودیت‌های-شناخته‌شده)


---

## 1. پروژه چیست و چگونه کار می‌کند

کاربر **یک فایل ZIP یا RAR** شامل چند فایل صوتی و **یک آدرس ایمیل** می‌دهد. سیستم برای هر فایل:

1. گفتار فارسی را با **Faster-Whisper** به متن تبدیل می‌کند،
2. یک **PDF جداگانه** (فارسی، راست‌به‌چپ) می‌سازد،
3. با یک **مدل زبانی محلی (Ollama)** اطلاعات ساختاریافته (خلاصه، تصمیمات، اقدامات…) استخراج می‌کند،
4. نتیجه را **ایمیل** می‌کند.

همه‌چیز روی سرور/کامپیوتر خودتان اجرا می‌شود و به سرویس هوش مصنوعی ابری پولی نیاز ندارد.

**اجزای برنامه**

| جزء | کار |
|---|---|
| `web` | رابط کاربری و API (Django) |
| `worker` | پردازش سنگین: تبدیل گفتار، PDF، مدل زبانی، ایمیل (Celery) |
| `beat` | بازیابی خودکار کارهای نیمه‌تمام و پاک‌سازی (Celery Beat) |
| `redis` | صف کارها (در حالت لوکال بدون Redis هم می‌شود اجرا کرد) |
| `db` | پایگاه‌داده (PostgreSQL در Docker، SQLite در حالت لوکال) |
| `ollama` | اجرای مدل زبانی |

**منابع لازم**

| | حداقل | پیشنهادی |
|---|---|---|
| RAM | 8 گیگابایت (بدون برنامه‌های سنگین دیگر) | 16 گیگابایت یا بیشتر |
| CPU | 4 هسته | 8 هسته |
| دیسک | 10 گیگابایت آزاد | 30 گیگابایت |
| GPU | لازم نیست | اختیاری (شتاب‌دهی) |

سرعت روی لپ‌تاپ 4 هسته‌ای که با آن آزمایش شد: هر فایل صوتی 25 ثانیه‌ای حدود **4 تا 6 دقیقه**. اولین کار چند دقیقه بیشتر طول می‌کشد، چون مدل گفتار دانلود می‌شود.

---

## 2. اجرای لوکال (ویندوز)

### 2.1 نصب برنامه‌های لازم
| برنامه | لینک | توضیح |
|---|---|---|
| Python 3.12 | https://www.python.org/downloads/ | هنگام نصب گزینهٔ **Add python.exe to PATH** را بزنید |
| Ollama | https://ollama.com/download | اجرای مدل زبانی |
| 7-Zip (اختیاری) | https://www.7-zip.org | فقط برای فایل‌های **RAR فشرده**؛ `7z.exe` را به PATH اضافه کنید. ZIP به چیزی نیاز ندارد |
| FFmpeg (اختیاری) | https://ffmpeg.org/download.html | پاک‌سازی بهتر صدا؛ بدون آن هم کار می‌کند |

اینترنت فقط برای بار اول لازم است (حدود 1.9 گیگابایت مدل زبانی و 1.5 گیگابایت مدل گفتار).

### 2.2 دریافت پروژه
پوشهٔ `audio-intelligence` را روی سیستم کپی کنید (مثلاً `C:\audio-intelligence`).
**این‌ها را کپی نکنید:** `.venv`، `media`، `db.sqlite3`، `.env.local`، `.env` (مخصوص همان سیستم‌اند).

در PowerShell:
```powershell
cd C:\audio-intelligence
```

### 2.3 ساخت محیط پایتون
```powershell
python -m venv .venv
```
```powershell
.\.venv\Scripts\Activate.ps1
```
اگر خطای «running scripts is disabled» آمد (فقط برای همین پنجره، بدون تغییر دائمی):
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```
اگر فعال‌سازی درست باشد، ابتدای خط فرمان `(.venv)` دیده می‌شود. **در هر ترمینال جدید باید دوباره فعال کنید.**

```powershell
pip install -r requirements.in pywin32
```
> `requirements.in` برای ویندوز است. `requirements.txt` نسخهٔ قفل‌شده برای لینوکس/Docker است. `pywin32` فقط برای اجرای بدون Redis لازم است.

### 2.4 دانلود مدل زبانی
```powershell
ollama pull qwen2.5:3b
```
بررسی کنید سرور Ollama جواب می‌دهد:
```powershell
curl http://127.0.0.1:11434/api/version
```
**اگر جواب نداد** (بعد از ریستارت، وقتی WSL/Docker نصب است، ویندوز ممکن است پورت را رزرو کرده باشد و در لاگ Ollama عبارت `forbidden by its access permissions` ببینید): Ollama را روی پورت دیگری اجرا کنید و آن پنجره را باز نگه دارید:
```powershell
$env:OLLAMA_HOST = '127.0.0.1:18434'; ollama serve
```
و در مرحلهٔ بعد `LLM_BASE_URL` را تنظیم کنید.

### 2.5 فایل تنظیمات محلی
فایلی به نام **`.env.local`** کنار `manage.py` بسازید (در git نمی‌رود، رمزها را اینجا بگذارید):
```
CELERY_FILESYSTEM_BROKER_DIR=media/.broker
# فقط اگر در مرحلهٔ قبل پورت دیگری استفاده کردید:
# LLM_BASE_URL=http://127.0.0.1:18434
```

### 2.6 آماده‌سازی و بررسی
```powershell
python manage.py migrate
```
```powershell
python manage.py validate_config
```
```powershell
python manage.py check_llm
```
* `validate_config` باید با `Configuration is valid.` تمام شود.
* `check_llm` باید بگوید Ollama در دسترس است و مدل نصب است.
* دو هشدار دربارهٔ FFmpeg و ابزار RAR اگر نصب نکرده‌اید عادی است. هشدار `audio.W003` یعنی ایمیل واقعی تنظیم نشده (بخش 4).

### 2.7 اجرا: سه پنجرهٔ PowerShell
در هر پنجره: `cd` به پوشهٔ پروژه، فعال‌سازی venv، سپس یک دستور:

**پنجرهٔ ۱: وب**
```powershell
python manage.py runserver
```
**پنجرهٔ ۲: ورکر** (همهٔ پردازش اینجا انجام می‌شود)
```powershell
celery -A config worker --pool=solo --loglevel=INFO
```
**پنجرهٔ ۳: بیت**
```powershell
celery -A config beat --loglevel=INFO --schedule media/.celerybeat-schedule
```
در پنجرهٔ ورکر باید ببینید: `LLM preflight: Ollama ... is reachable and model 'qwen2.5:3b' is installed`.

> در VS Code: پروژه را با **File → Open Folder** باز کنید، در Run and Debug گزینهٔ **Run all (web + worker + beat)** را انتخاب و F5 بزنید.

### 2.8 استفاده
1. آدرس **http://localhost:8000** را باز کنید.
2. فایل ZIP/RAR را بکشید و رها کنید، ایمیل را بنویسید، دکمهٔ ارسال را بزنید.
3. صفحهٔ وضعیت خودش به‌روز می‌شود. وقتی تمام شد، پیام فارسی و دکمهٔ **دریافت PDF** برای هر فایل نمایش داده می‌شود.
4. مستندات API: http://localhost:8000/api/docs/

**فایل نمونه:** `samples/sample-meeting.zip` (سه فایل mp3 فارسی، یک جلسهٔ کوتاه). برای تست سریع‌تر فقط `reza.mp3` را ZIP کنید.

### 2.9 توقف و اجرای دوباره
در هر پنجره `Ctrl+C`. برای اجرای دوباره همان مرحلهٔ 2.7 (Ollama هم باید روشن باشد). داده‌ها در پوشهٔ `media` می‌مانند.

### 2.10 (اختیاری) اجرای لوکال با Docker
ببینید `docs\DOCKER.md` یا بخش 3؛ فرق‌ها: به‌جای سرور، روی همین سیستم؛ آدرس **http://localhost:8000**؛ ایمیل و دامنه لازم نیست.

---

## 3. اجرا روی سرور ابری

هدف: برنامه روی یک سرور لینوکس با **دامنهٔ خودتان و HTTPS** در دسترس باشد.

### 3.1 انتخاب سرور
* **سیستم‌عامل:** Ubuntu 22.04 یا 24.04.
* **منابع:** حداقل 4 vCPU و **8 گیگابایت RAM** (با swap)؛ **پیشنهادی 8 vCPU و 16 گیگابایت**. مدل گفتار (حدود 2 گیگابایت) و مدل زبانی (حدود 2.5 گیگابایت) هر دو در RAM هستند.
* **دیسک:** حداقل 40 گیگابایت.
* **GPU لازم نیست.** نسخهٔ پیش‌فرض فقط CPU است (شتاب‌دهی GPU در بخش 3.12).
* سرور باید به اینترنت وصل باشد (دانلود مدل‌ها و ایمیل).

### 3.2 دامنه و DNS
یک رکورد **A** بسازید که دامنه (مثلاً `audio.example.com`) را به IP سرور وصل کند. صبر کنید تا DNS اعمال شود:
```bash
nslookup audio.example.com
```

### 3.3 آماده‌سازی سرور
با SSH وارد شوید و دستورها را اجرا کنید.

**به‌روزرسانی و فایروال** (قبل از فعال‌سازی، مطمئن شوید SSH مجاز است تا از سرور بیرون نیفتید):
```bash
sudo apt update && sudo apt upgrade -y
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

**نصب Docker** (اسکریپت رسمی Docker؛ اگر ترجیح می‌دهید ابتدا اسکریپت را بخوانید: https://get.docker.com):
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```
بعد از آن یک بار خارج و دوباره وارد شوید و بررسی کنید:
```bash
docker version
docker compose version
```

**فضای swap** (برای جلوگیری از کم‌آوردن RAM؛ اگر RAM کمتر از 16 گیگابایت است توصیه می‌شود):
```bash
sudo fallocate -l 8G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 3.4 انتقال پروژه به سرور
از کامپیوتر خودتان (PowerShell). پوشه‌های سنگین و مخصوص سیستم را نفرستید:
```powershell
cd C:\audio-intelligence
tar --exclude=.venv --exclude=media --exclude=db.sqlite3 --exclude=.env --exclude=.env.local --exclude=graphify-out --exclude=__pycache__ --exclude=node_modules -czf ..\audio-intelligence.tgz .
scp ..\audio-intelligence.tgz user@SERVER_IP:~
```
روی سرور:
```bash
mkdir -p ~/audio-intelligence && tar -xzf ~/audio-intelligence.tgz -C ~/audio-intelligence
cd ~/audio-intelligence
```
(اگر پروژه را در git دارید، می‌توانید به‌جای این مراحل `git clone` کنید.)

### 3.5 ساخت فایل `.env` روی سرور
**هرگز `.env` یک سیستم دیگر را کپی نکنید؛ روی سرور خودتان رمزهای جدید بسازید.**
```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
nano .env
```
مقدارهای زیر را در `.env` بگذارید (خروجی دستور اول برای `DJANGO_SECRET_KEY` و دومی برای `POSTGRES_PASSWORD`):

```
DJANGO_SECRET_KEY=<خروجی اول>
POSTGRES_PASSWORD=<خروجی دوم>
DB_ENGINE=postgres

# دامنهٔ شما
DJANGO_ALLOWED_HOSTS=audio.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://audio.example.com
SITE_BASE_URL=https://audio.example.com

# پشت پروکسی HTTPS هستیم
DJANGO_SECURE_SSL_REDIRECT=false
DJANGO_SECURE_COOKIES=true
DJANGO_BEHIND_PROXY=true

# مدل زبانی داخل Docker
DOCKER_LLM_BASE_URL=http://ollama:11434

# ایمیل واقعی (بخش 4)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL=Audio Intelligence <no-reply@example.com>
```
توضیح: `DJANGO_SECURE_SSL_REDIRECT=false` چون هدایت به HTTPS را پروکسی انجام می‌دهد؛ `DJANGO_BEHIND_PROXY=true` باعث می‌شود Django هدر `X-Forwarded-Proto` پروکسی را بپذیرد. فایل را فقط خودتان بخوانید: `chmod 600 .env`.

### 3.6 ساخت و اجرا
```bash
docker compose --profile ollama build
docker compose --profile ollama up -d
docker compose ps
```
منتظر بمانید `web` به وضعیت `healthy` برسد (30 تا 60 ثانیه). مهاجرت پایگاه‌داده هنگام شروع `web` خودکار انجام می‌شود.

پورت 8000 فقط روی `127.0.0.1` سرور باز است، نه اینترنت (عمداً؛ دسترسی عمومی از راه پروکسی در بخش 3.8).

### 3.7 دانلود مدل زبانی داخل Docker
```bash
docker compose exec ollama ollama pull qwen2.5:3b
docker compose exec worker python manage.py check_llm
```
خروجی دوم باید بگوید Ollama در دسترس و مدل نصب است. مدل در volume `ollama` می‌ماند و دوباره دانلود نمی‌شود. مدل گفتار (Whisper) اولین بار هنگام اولین کار دانلود و در volume `models` ذخیره می‌شود.

### 3.8 HTTPS با Caddy (گواهی خودکار Let's Encrypt)
روی سرور (نصب رسمی Caddy):
```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```
فایل `/etc/caddy/Caddyfile` را با این محتوا بسازید (دامنه را عوض کنید):
```
audio.example.com {
    request_body {
        max_size 520MB
    }
    reverse_proxy 127.0.0.1:8000
}
```
`520MB` کمی بیشتر از سقف آپلود برنامه (500 مگابایت، تنظیم `uploads.max_archive_bytes` در `config/app.yaml`) است.
```bash
sudo systemctl reload caddy
```
اکنون **https://audio.example.com** را باز کنید. (پورت‌های 80 و 443 باید باز و DNS درست باشد.)

### 3.9 محدود کردن دسترسی (بسیار مهم برای سرور عمومی)
برنامه **حساب کاربری و لاگین ندارد**؛ هر کسی که آدرس را بداند می‌تواند فایل بفرستد، و هر پردازش چند دقیقه CPU مصرف می‌کند. محدودیت نرخ (به‌طور پیش‌فرض 20 آپلود در ساعت برای هر IP) وجود دارد، ولی برای سرور عمومی کافی نیست. ساده‌ترین راه، رمز عبور روی صفحهٔ آپلود با Caddy است:

```bash
caddy hash-password
```
(رمز را می‌پرسد و یک هش چاپ می‌کند.) سپس در Caddyfile:
```
audio.example.com {
    request_body {
        max_size 520MB
    }
    @guarded path / /upload/ /api/v1/jobs/
    basic_auth @guarded {
        admin <هش_چاپ‌شده>
    }
    reverse_proxy 127.0.0.1:8000
}
```
فقط صفحهٔ آپلود و endpoint های آپلود محافظت می‌شوند. صفحهٔ وضعیت و لینک‌های امضاشدهٔ داخل ایمیل بدون رمز کار می‌کنند، چون گیرندهٔ ایمیل باید بتواند PDF را باز کند. گزینه‌های دیگر: محدود کردن به IP های مشخص با `ufw`، یا قرار دادن سرور پشت VPN.

### 3.10 آزمایش نهایی روی سرور
از کامپیوتر خودتان (فایل نمونه را آپلود کنید؛ اگر رمز گذاشته‌اید `-u admin:رمز` اضافه کنید):
```bash
curl -F "file=@samples/sample-meeting.zip" -F "email=you@example.com" https://audio.example.com/api/v1/jobs/
```
پاسخ باید `202` و یک `job_id` و `access_token` باشد. وضعیت:
```bash
curl -H "Authorization: Bearer <access_token>" https://audio.example.com/api/v1/jobs/<job_id>/
```
پیشرفت را در ورکر ببینید:
```bash
docker compose logs -f worker
```
وقتی تمام شد: وضعیت `COMPLETED`، ایمیل رسیده، و PDF ها قابل دانلود هستند.

### 3.11 نگهداری

| کار | دستور |
|---|---|
| وضعیت سرویس‌ها | `docker compose ps` |
| لاگ یک سرویس | `docker compose logs -f web` (یا `worker`، `beat`) |
| توقف (داده می‌ماند) | `docker compose --profile ollama stop` |
| شروع دوباره | `docker compose --profile ollama start` |
| اعمال تغییر در `config/` یا کد | فایل‌ها را روی سرور عوض کنید، سپس `docker compose --profile ollama up -d --build` (تنظیمات داخل image پخته می‌شوند) |
| کار ناموفق را دوباره اجرا کنید (مثلاً Ollama خاموش بود) | `docker compose exec worker python manage.py reprocess_job <job_id>` |
| ⚠️ حذف همه‌چیز از جمله داده‌ها | `docker compose down -v` (فقط در صورت اطمینان!) |

**پشتیبان‌گیری** (داده‌ها در volume هاست: `pgdata` پایگاه‌داده، `media` آرشیوها و PDF ها):
```bash
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup-$(date +%F).sql
docker run --rm -v audio-intelligence_media:/data -v "$PWD":/backup alpine tar czf /backup/media-$(date +%F).tgz -C /data .
```
نام volume به نام پوشهٔ پروژه بستگی دارد (`docker volume ls` را ببینید). بدانید که آرشیوهای آپلود‌شده و PDF ها خودکار پاک می‌شوند (آرشیو بعد از حداقل یک ساعت و پایان پردازش، PDF ها بعد از 7 روز؛ قابل تنظیم در `config/app.yaml`).

### 3.12 گزینه‌ها
* **GPU (انویدیا):** NVIDIA Container Toolkit را نصب کنید، در `config/ai/stt.yaml` مقدار `device: cuda` و `compute_type: float16` بگذارید، در `config/ai/settings.yaml` خط `num_gpu: 0` را بردارید، و با فایل `docker-compose.gpu.yml` اجرا کنید (کتابخانه‌های CUDA باید در image باشند؛ جزئیات در همان فایل). این مسیر آزمایش نشده است.
* **مدل زبانی روی سرور دیگر:** در `config/ai/settings.yaml` مقدار `llm.base_url` (یا متغیر `DOCKER_LLM_BASE_URL`) را به آن سرور بدهید. اگر از سرویس خارجی (`openai_compatible`) استفاده کنید، **متن فایل‌های شما به آن سرویس فرستاده می‌شود**؛ فقط با آگاهی از این موضوع.
* **Redis و PostgreSQL** در همین compose هستند و نیاز به تنظیم جدا ندارند.

---

## 4. تنظیم ایمیل

بدون تنظیم SMTP، ایمیل‌ها **فقط در پنجرهٔ ورکر چاپ می‌شوند** و صفحهٔ وضعیت صریحاً می‌گوید «ایمیل واقعی ارسال نشد» (PDF ها همچنان قابل دانلود هستند).

* **لوکال:** خطوط SMTP را در `.env.local` بگذارید (قالب کامنت‌شده در فایل هست) و ورکر را دوباره اجرا کنید.
* **سرور:** در `.env` و سپس `docker compose --profile ollama up -d`.

نمونه (Gmail؛ رمز عادی کار نمی‌کند، **App Password** بسازید):
```
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=you@gmail.com
EMAIL_HOST_PASSWORD=<app password>
DEFAULT_FROM_EMAIL=Audio Intelligence <you@gmail.com>
```
نکات:
* بسیاری از ارائه‌دهندگان ابری **پورت 25 را مسدود** می‌کنند؛ از 587 با یک سرویس ایمیل (Gmail، Mailgun، SendGrid، Amazon SES و…) استفاده کنید.
* «پذیرفته شدن توسط SMTP» به معنی «رسیدن به صندوق ورودی» نیست (ممکن است اسپم شود).
* همهٔ PDF ها در **یک فایل ZIP** (`results-<شناسه>.zip`) به ایمیل پیوست می‌شوند (اگر حجم ZIP کمتر از 15 مگابایت باشد)؛ در غیر این صورت **لینک امضاشدهٔ دانلود ZIP** با اعتبار 7 روز در ایمیل می‌آید. همین ZIP را از دکمهٔ «دریافت همه PDFها» در صفحهٔ وضعیت هم می‌توانید بگیرید. برای پیوست جداگانهٔ هر PDF: `attach_format: pdf` در `config/app.yaml`.
* ایمیل موقتاً ناموفق (خطاهای 4xx و قطعی شبکه) تا حدود 15 دقیقه دوباره تلاش می‌شود و ایمیل تکراری ارسال نمی‌شود.
* **تست سریع تنظیمات SMTP:** `python manage.py send_test_email you@example.com` (یک پیام کوتاه) یا `python manage.py send_test_email you@example.com --job latest` (ایمیل واقعیِ آخرین کار تمام‌شده، همراه ZIP). وضعیت کار تغییر نمی‌کند.
* تست بدون حساب واقعی: `python scripts/smtp_sink.py --port 2525` و `EMAIL_HOST=127.0.0.1`, `EMAIL_PORT=2525`, `EMAIL_USE_TLS=false`؛ پیام‌ها در `media/smtp-sink` ذخیره می‌شوند.

---

## 5. تغییر مدل، فیلدهای استخراج، پرامپت و PDF

همه در پوشهٔ `config/` است؛ **بدون تغییر کد پایتون**. بعد از تغییر، سرویس‌ها را دوباره راه بیندازید (در Docker: `up -d --build`).

| چه می‌خواهید | فایل |
|---|---|
| مدل زبانی، provider، timeout، دما | `config/ai/settings.yaml` (`llm:`) |
| فیلدهای قابل استخراج | `config/ai/extraction_schema.json` |
| دستورهای مدل | `config/ai/prompts/*.txt` |
| ظاهر و محتوای PDF | `config/ai/pdf_template.yaml` |
| مدل گفتار (`small` / `medium` / `large-v3`)، زبان | `config/ai/stt.yaml` |
| محدودیت‌ها، نگهداری فایل، تعداد تلاش مجدد | `config/app.yaml` |

نکته‌ها:
* مدل گفتار پیش‌فرض `medium` است (روی نمونه‌های آزمایشی خطای کلمه حدود 30٪ در برابر 46٪ برای `small`). اگر RAM کم است `small` بگذارید.
* در schema، فیلدهایی که با `"x-grounded": true` علامت خورده‌اند با متن تطبیق داده می‌شوند و مقدارهای ساختگی («نامشخص» و…) حذف می‌شوند.
* قبل از اعمال: `python manage.py validate_config` (در Docker: `docker compose exec web python manage.py validate_config`).

---

## 6. آزمایش و راستی‌آزمایی

**آزمون‌های خودکار** (بدون مدل، Redis و ایمیل؛ حدود 90 ثانیه):
```powershell
pip install pytest pytest-django
python -m pytest
```
باید **162 passed** ببینید (3 آزمون «integration» عمداً رد می‌شوند).

**آزمون با مدل‌های واقعی** (Ollama روشن و مدل نصب):
```powershell
$env:RUN_INTEGRATION = '1'; python -m pytest tests/integration -m integration -s
```

**سنجش کیفیت تبدیل گفتار** روی ضبط‌های خودتان: برای هر فایل `x.mp3` یک `x.txt` (متن درست) در `tests/samples` بگذارید:
```powershell
python scripts/evaluate_transcription.py tests/samples --model small --model medium
```
(متن‌های مرجع فعلی در `tests/samples` را من از روی خروجی بازسازی کرده‌ام، نه با شنیدن صدا؛ برای سنجش واقعی، متن تأییدشدهٔ انسانی بگذارید.)

---

## 7. عیب‌یابی

| نشانه | علت و راه‌حل |
|---|---|
| کار در حالت «queued» می‌ماند | ورکر اجرا نیست، یا از داخل پوشهٔ پروژه اجرا نشده (`.env.local` خوانده نمی‌شود). لاگ ورکر را ببینید. بیت هم بعد از چند دقیقه خودش دوباره صف می‌کند. |
| نتیجه «ناقص» است و در PDF نوشته «استخراج اطلاعات انجام نشد» | مدل زبانی در دسترس نبود. `python manage.py check_llm` (Docker: `docker compose exec worker python manage.py check_llm`). بعد از رفع: `reprocess_job <job_id>`. |
| `Ollama ... bind: forbidden by its access permissions` (ویندوز) | پورت رزرو شده؛ Ollama را روی پورت دیگر اجرا کنید (2.4). |
| صفحه می‌گوید «ایمیل واقعی ارسال نشد» | SMTP تنظیم نشده (بخش 4). |
| ایمیل `FAILED` شد ولی PDF ها هست | تنظیمات SMTP یا دسترسی شبکه را بررسی کنید؛ PDF ها از صفحهٔ وضعیت قابل دانلودند. |
| حافظه تمام می‌شود / ورکر `exit 137` | RAM کم است: swap اضافه کنید، برنامه‌های دیگر را ببندید، یا `model: small` در `stt.yaml`. |
| بسیار کند | CPU ضعیف است؛ مدل گفتار کوچک‌تر، یا استخراج اطلاعات را خاموش کنید (`ai.extraction.enabled: false`). |
| `DisallowedHost` یا خطای CSRF روی سرور | `DJANGO_ALLOWED_HOSTS` و `DJANGO_CSRF_TRUSTED_ORIGINS` را با آدرس دقیق (با `https://`) تنظیم کنید. |
| آپلود فایل بزرگ خطای 413 می‌دهد | `request_body max_size` در Caddyfile و `uploads.max_archive_bytes` در `config/app.yaml`. |
| ساخت Docker روی `apt-get` یا `pip` خطای شبکه می‌دهد | مشکل شبکه یا DNS؛ دوباره `docker compose build` را اجرا کنید (از cache ادامه می‌دهد). |
| `ModuleNotFoundError` (لوکال) | venv فعال نیست یا مرحلهٔ 2.3 انجام نشده. |
| آپلود RAR خطا می‌دهد | 7-Zip نصب و به PATH اضافه شود، یا ZIP بفرستید (در Docker نصب شده است). |

---

## 8. محدودیت‌های شناخته‌شده

برای اینکه انتظارات درست باشد:

* **مسیر Docker و سرور ابری آزمایش نشده است.** فایل‌های `Dockerfile` و `docker-compose.yml` نوشته و اعتبارسنجی شده‌اند (`docker compose config` بدون خطا)، ولی ساخت کامل image و اجرای کل stack روی یک سرور واقعی انجام نشده؛ ساخت یک‌بار نیمه‌کاره ماند. اولین اجرای شما ممکن است به رفع مشکل کوچکی نیاز داشته باشد.
* **ایمیل واقعی** فقط در برابر یک سرور SMTP محلی آزمایشی (شامل خطای موقت و تلاش مجدد) راستی‌آزمایی شده؛ رسیدن به صندوق ورودی واقعی بررسی نشده است.
* **دقت فارسی کامل نیست.** Whisper `medium` روی نمونه‌ها حدود 30٪ خطای کلمه داشت. نام‌ها، اصطلاحات فنی، چند گوینده و صدای نویزی خطای بیشتر دارند. مدل زبانی کوچک (3B) هم گاهی دسته‌بندی را اشتباه می‌کند (مثلاً «حدود دو روز» را هم تاریخ و هم عدد می‌نویسد).
* **RAR فشرده** فقط با ابزار 7-Zip/unrar کار می‌کند و روی این سیستم آزمایش نشده (RAR بدون فشرده‌سازی آزمایش شده).
* **حساب کاربری وجود ندارد.** دسترسی هر کار با یک توکن/نشست است؛ برای سرور عمومی حتماً بخش 3.9 را انجام دهید.
* **سرعت:** روی CPU کند است (چند دقیقه برای هر فایل کوتاه). فایل‌های طولانی (مثلاً ساعت‌ها) زمان زیادی می‌برند؛ برای حجم بالا GPU یا سرور قوی‌تر لازم است.
* **متن‌های طولانی** برای مدل زبانی به اندازهٔ پنجرهٔ زمینه بریده می‌شوند (PDF همیشه متن کامل را دارد).

مستندات تکمیلی: `README.md` (معماری و نمودارها)، `SECURITY.md` (یافته‌های امنیتی)، `docs/DECISIONS.md` (تصمیم‌های فنی)، `docs/DOCKER.md` (Docker).
