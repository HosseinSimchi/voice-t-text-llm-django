# Setup guide: run the project on a new Windows machine

For someone who has never seen the project. Takes about 30 minutes plus model downloads.

## What it does
You upload one ZIP/RAR of audio files and an e-mail address. The app transcribes each file (Persian), builds one PDF per file,
extracts structured information with a local AI model, and e-mails the results. Everything runs on your computer.

## 0. Requirements
| Need | Notes |
|---|---|
| Windows 10/11, **8 GB RAM minimum (16 GB recommended)**, ~10 GB free disk | Each 25-second file takes about 4-6 minutes on a 4-core laptop CPU. |
| **Python 3.12** | https://www.python.org/downloads/ (tick "Add python.exe to PATH") |
| **Ollama** | https://ollama.com/download |
| Internet (first run only) | Downloads ~1.9 GB (LLM) and ~1.5 GB (Whisper model). |
| *Optional:* 7-Zip | Only to accept **.rar** archives that are compressed. Add `7z.exe` to PATH. ZIP needs nothing. |
| *Optional:* FFmpeg | Slightly better audio cleanup. The app works without it. |

## 1. Get the project
Copy the folder `audio-intelligence` to the new machine (for example `C:\audio-intelligence`). Do **not** copy `.venv`, `media`, `db.sqlite3` or `.env.local`; they are specific to the old machine.

Open **PowerShell** in that folder:
```powershell
cd C:\audio-intelligence
```

## 2. Create the Python environment
```powershell
python -m venv .venv
```
```powershell
.\.venv\Scripts\Activate.ps1
```
If PowerShell says "running scripts is disabled", run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and activate again.
Your prompt now starts with `(.venv)`. Repeat the activation in every new terminal.

```powershell
pip install -r requirements.in pywin32
```
(`pywin32` lets the app run without Redis on Windows. `requirements.txt` is the pinned Linux/Docker set; use `requirements.in` on Windows.)

## 3. Install the AI model (Ollama)
After installing Ollama:
```powershell
ollama pull qwen2.5:3b
```
Check that the server answers:
```powershell
curl http://127.0.0.1:11434/api/version
```
**If that fails** (common after a reboot with WSL/Docker installed): Windows may have reserved the port. Start Ollama on another port in its own terminal and keep it open:
```powershell
$env:OLLAMA_HOST = '127.0.0.1:18434'; ollama serve
```
and use `LLM_BASE_URL=http://127.0.0.1:18434` in step 4.

## 4. Create your local settings file
Create a file named **`.env.local`** in the project folder:
```
CELERY_FILESYSTEM_BROKER_DIR=media/.broker
# Only if you used another Ollama port in step 3:
# LLM_BASE_URL=http://127.0.0.1:18434
```
Real e-mail settings are added later (step 8). Without them e-mails are only printed in the worker window.

## 5. Prepare the database and check everything
```powershell
python manage.py migrate
```
```powershell
python manage.py validate_config
```
```powershell
python manage.py check_llm
```
`validate_config` must end with "Configuration is valid." and `check_llm` with "reachable and model 'qwen2.5:3b' is installed". Fix any error message before going on.
Two warnings about FFmpeg and a RAR tool are normal if you did not install them.

## 6. Start the three processes
Open **three PowerShell windows**. In each: `cd` to the project and activate the venv (step 2). Then run one command per window.

**Window 1: web server**
```powershell
python manage.py runserver
```
**Window 2: worker** (does all the processing)
```powershell
celery -A config worker --pool=solo --loglevel=INFO
```
**Window 3: beat** (automatic recovery and cleanup)
```powershell
celery -A config beat --loglevel=INFO --schedule media/.celerybeat-schedule
```
The worker window should show `LLM preflight: ... reachable and model 'qwen2.5:3b' is installed`.

## 7. Use it
1. Open **http://localhost:8000**
2. Drop a ZIP/RAR of audio (mp3, wav, m4a, aac, ogg, flac, opus) and type your e-mail.
3. Press **Submit**. You are taken to a status page that updates by itself.
4. **First job only:** the Whisper model downloads and loads (a few extra minutes).
5. When finished, the page shows a Persian message and a **Download PDF** button per file.

API documentation: http://localhost:8000/api/docs/

## 8. Send real e-mail
Edit `.env.local`, add your provider's settings, then restart the worker (Ctrl+C, run the command again):
```
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=you@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=Audio Intelligence <you@gmail.com>
```
Gmail needs an *app password*, not your normal password. Never share or commit `.env.local`.
Until this is set, the page says that **no real e-mail was sent**; the PDFs can still be downloaded from the page.
To test without an account: run `python scripts/smtp_sink.py --port 2525` in a fourth window and use `EMAIL_HOST=127.0.0.1`, `EMAIL_PORT=2525`, `EMAIL_USE_TLS=false`. Mails are saved in `media\smtp-sink`.

## 9. Stopping and restarting
Press `Ctrl+C` in each window. To start again, repeat step 6 (and keep Ollama running). Uploaded data lives in the `media` folder.

## 10. Problems
| Symptom | Fix |
|---|---|
| Page says processing is "partial", PDFs say extraction was not done | The AI model was unreachable. Run `python manage.py check_llm`, fix Ollama, then `python manage.py reprocess_job <job id>` (the id is shown on the status page). |
| Job stays "queued" | The worker window is not running, or it was started without `.env.local` (start it from the project folder). |
| `Ollama ... bind: forbidden by its access permissions` | Use another port (step 3). |
| Out of memory / very slow | Close other programs. In `config\ai\stt.yaml` set `model: small` (faster, less accurate). |
| `ModuleNotFoundError` | The venv is not active, or step 2 was skipped. |
| RAR upload fails | Install 7-Zip and add it to PATH, or upload a ZIP. |

## 11. Optional: run the tests
```powershell
pip install pytest pytest-django
```
```powershell
python -m pytest
```
146 tests, about 90 seconds. They need no models, Redis or e-mail account.

## Docker instead
See `docs\DOCKER.md`. Note: the Docker setup was written but has **not been fully built and tested** yet.
