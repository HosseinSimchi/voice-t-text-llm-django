# Running with Docker — step by step (Windows + Docker Desktop)

All commands run from the project folder `F:\ai-agent-codes\audio-intelligence`
(PowerShell, Git Bash or the VS Code terminal).

## What runs where

| Service | Where | Notes |
|---|---|---|
| `web` | container | Django + Gunicorn on http://localhost:8000 (runs migrations on start) |
| `worker` | container | Celery: FFmpeg, Whisper, PDFs, LLM calls, email |
| `beat` | container | Celery Beat: recovery every 2 min, cleanup every 10 min |
| `db` | container | PostgreSQL 16 (volume `pgdata`) |
| `redis` | container | Broker with AOF persistence (volume `redisdata`) |
| Ollama | **your Windows host** (default) | Containers reach it at `http://host.docker.internal:11434` |

Running Ollama on the host saves about 2.5 GB of Docker memory and reuses the model you already downloaded.
To run Ollama inside Docker instead, see [step 9](#9-optional-ollama-inside-docker).

## 1. Start Docker Desktop
Open **Docker Desktop** and wait until it shows *Engine running*. Check it:
```bash
docker info --format "{{.ServerVersion}} CPUs={{.NCPU}} Mem={{.MemTotal}}"
```
Docker gets about 3.6 GB of memory on an 8 GB machine, which is enough for this stack with host Ollama.
To give it more, edit `%UserProfile%\.wslconfig` (`[wsl2]` then `memory=5GB`) and restart Docker Desktop.

## 2. Make sure Ollama runs on the host and has the model
```bash
ollama list
```
If `qwen2.5:3b` is missing:
```bash
ollama pull qwen2.5:3b
```

## 3. Create `.env`
```bash
cp .env.example .env
```
Edit `.env`:
* `DJANGO_SECRET_KEY`: a long random value, for example from `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
* `POSTGRES_PASSWORD`: any strong password.
* `DB_ENGINE=postgres`
* For local plain HTTP, keep `DJANGO_SECURE_SSL_REDIRECT=false` and `DJANGO_SECURE_COOKIES=false`.
* Email: `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend` prints emails in the worker log.
  For real email, set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` and fill in `EMAIL_HOST`, `EMAIL_PORT`,
  `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` and `DEFAULT_FROM_EMAIL`.

`.env` holds secrets. It is git-ignored and excluded from the image.

## 4. Build the image
```bash
docker compose build
```
The first build downloads the Python base image, FFmpeg/7zip and the Python packages (several hundred MB).

## 5. Start the stack
```bash
docker compose up -d
```
```bash
docker compose ps
```
Wait until `web` is `healthy` (about 30–60 s). Open **http://localhost:8000**. API docs: http://localhost:8000/api/docs/.

## 6. Watch the processing
```bash
docker compose logs -f worker
```
The first transcription downloads the Whisper `small` model (about 460 MB) into the `models` volume. Later jobs reuse it.
With the console email backend, the result email appears in this log.

## 7. Everyday commands
| Task | Command |
|---|---|
| Stop (keep data) | `docker compose stop` |
| Start again | `docker compose start` |
| Stop and remove containers (keep data) | `docker compose down` |
| Rebuild after code changes | `docker compose up -d --build` |
| Apply config changes (`config/*.yaml`) | `docker compose up -d --build` (config files are baked into the image) |
| Validate configuration | `docker compose exec web python manage.py validate_config` |
| Django shell | `docker compose exec web python manage.py shell` |
| Logs of one service | `docker compose logs -f web` |
| **Delete everything incl. data** | `docker compose down -v`, which removes archives, PDFs, the database and models |

## 8. Where the data lives
Docker volumes: `media` (archives, results, temporary files), `pgdata`, `redisdata`, `models` (Whisper cache), `logs`.
They survive `down`, restarts and rebuilds. Only `down -v` removes them.

## 9. (Optional) Ollama inside Docker
Needs about 3 GB more Docker memory. In `.env`, add:
```
DOCKER_LLM_BASE_URL=http://ollama:11434
```
Then run:
```bash
docker compose --profile ollama up -d
```
```bash
docker compose exec ollama ollama pull qwen2.5:3b
```

## Troubleshooting
| Problem | Fix |
|---|---|
| `apt-get` / `pip` download errors during build | Network or DNS issue. Run `docker compose build` again (downloads resume from cache). |
| Jobs fail with `llm_unavailable` | Host Ollama not running, or not reachable from containers. Test: `docker compose exec worker curl -s http://host.docker.internal:11434/api/version`. If it fails, set the Windows user env var `OLLAMA_HOST=0.0.0.0` and restart Ollama. That exposes Ollama on your LAN, so use the Windows firewall. |
| `web` restarting | `docker compose logs web`: usually a missing or short `DJANGO_SECRET_KEY` or a configuration error. |
| Worker killed (exit 137) | Out of memory: give Docker more memory (step 1) or use Whisper `base` in `config/ai/stt.yaml`. |
| `DisallowedHost` | Add the host name to `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` in `.env`. |
