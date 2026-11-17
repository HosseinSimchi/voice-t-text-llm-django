# Running with Docker

One image (`audio-intelligence`) runs `web`, `worker`, `beat` and the one-off `migrate` job; the compose file adds PostgreSQL, Redis and Ollama.
The image builds in a few minutes and is about **1.2 GB** (it contains no models and no secrets).

## What runs where

| Service | Image | Notes |
|---|---|---|
| `web` | `audio-intelligence` | Django + Gunicorn on `127.0.0.1:8000` (localhost only, see "Public access") |
| `worker` | `audio-intelligence` | Celery: FFmpeg, Whisper, PDFs, LLM calls, e-mail |
| `beat` | `audio-intelligence` | Celery Beat: recovery every 2 min, cleanup every 10 min |
| `migrate` | `audio-intelligence` | One-off: applies database migrations, then exits. `web`, `worker`, `beat` wait for it |
| `db` | `postgres:16-alpine` | Volume `pgdata` |
| `redis` | `redis:7-alpine` | Queue, AOF persistence, volume `redisdata` |
| `ollama` | `ollama/ollama` | Local LLM server (internal network only), volume `ollama` |
| `ollama-init` | `ollama/ollama` | One-off: downloads the model (default `qwen2.5:3b`, about 1.9 GB), then exits |

Start order: `db`, `redis`, `ollama` → `migrate`, `ollama-init` → `web`, `worker`, `beat`.

## Requirements
Docker Engine 24+ with Compose v2, **8 GB RAM minimum for the whole stack (16 GB recommended)**, 30 GB of disk, outbound internet on first run
(Whisper model from huggingface.co, LLM from the Ollama registry). On Docker Desktop, give Docker enough memory (Settings → Resources, or `memory=` in `%UserProfile%\.wslconfig`).

## Quick start

```bash
cp .env.example .env
```
Edit `.env`: set `DJANGO_SECRET_KEY` (a long random value) and `POSTGRES_PASSWORD`, `DB_ENGINE=postgres`, and your SMTP settings (see GUIDE.md).
For plain HTTP on one machine keep `DJANGO_SECURE_SSL_REDIRECT=false` and `DJANGO_SECURE_COOKIES=false`. Generate secrets with:
```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

```bash
docker compose up -d --build
```
The first start downloads the Ollama image and the LLM, so it takes a while. Watch it:
```bash
docker compose ps -a
docker compose logs -f ollama-init worker
```
When `web` is `healthy`, open **http://localhost:8000**. The first job also downloads the Whisper model (about 1.5 GB) into the `models` volume.

## For CI/CD

The app image is built once, by the `web` service, and reused by `migrate`, `worker` and `beat`.

```bash
docker build -t registry.example.com/team/audio-intelligence:1.0.0 .
docker push registry.example.com/team/audio-intelligence:1.0.0
```
or with compose:
```bash
APP_IMAGE=registry.example.com/team/audio-intelligence APP_TAG=1.0.0 docker compose build web
APP_IMAGE=registry.example.com/team/audio-intelligence APP_TAG=1.0.0 docker compose push web
```

What the pipeline and the runtime environment need to know:
* **No secrets are in the image.** Everything comes from environment variables at runtime (`DJANGO_SECRET_KEY`, `POSTGRES_*`, `REDIS_URL`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `SITE_BASE_URL`, `EMAIL_*`, `LLM_BASE_URL`; full list in `.env.example`).
* **Container commands** (first argument of the entrypoint): `web`, `worker`, `beat`, `migrate`, or `manage <args>`. Run `migrate` once per release **before** starting `web`/`worker`/`beat` (compose does this; in Kubernetes use a Job or init container).
* **Health:** `web` → `GET /healthz`; `worker` → `celery inspect ping` (in compose).
* **Volumes to persist:** `/app/media` (archives, results), `/app/models` (Whisper cache), `/app/logs`, plus PostgreSQL, Redis and Ollama data.
* **`config/*.yaml` and the prompts are baked into the image.** Changing the model, schema or prompts means a rebuild, or mount your own directory and set `APP_CONFIG_DIR` (do not mount over `/app/config`: it also holds the Python settings package).
* **Shutdown:** the worker has `stop_grace_period: 10m` so a running stage can finish.
* **Check line endings** before building on Windows: `python scripts/normalize_eol.py --check` (a CRLF `entrypoint.sh` makes the container fail to start). `.gitattributes` keeps them as LF in git.
* **Scan the image** with your usual tool (for example Trivy) as part of the pipeline.

## Everyday commands

| Task | Command |
|---|---|
| Status | `docker compose ps -a` |
| Logs of one service | `docker compose logs -f worker` |
| Stop (keep data) | `docker compose stop` |
| Start again | `docker compose start` |
| Rebuild after code/config changes | `docker compose up -d --build` |
| Validate the configuration | `docker compose exec web python manage.py validate_config` |
| Check the LLM | `docker compose exec worker python manage.py check_llm` |
| Re-run failed extractions of a job | `docker compose exec worker python manage.py reprocess_job <job_id>` |
| Test your SMTP settings | `docker compose exec worker python manage.py send_test_email you@example.com` |
| **Delete everything including data** | `docker compose down -v` |

## Public access (cloud server)
The web port is published on `127.0.0.1` only, because Docker would otherwise bypass the host firewall for published ports.
Put a TLS reverse proxy (Caddy, nginx) in front and add your domain to `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` and `SITE_BASE_URL`;
see **GUIDE.md section 3** for the full server walkthrough (firewall, HTTPS, password on the upload page). Set `WEB_BIND=0.0.0.0` only if something else protects the port.

## Choosing the LLM
* **Container (default):** Ollama runs in compose and `ollama-init` downloads the model named in `LLM_MODEL` (default `qwen2.5:3b`).
  **Keep `LLM_MODEL` equal to `llm.model` in `config/ai/settings.yaml`.**
* **Ollama on the host instead:** set `DOCKER_LLM_BASE_URL=http://host.docker.internal:11434` in `.env` and start with
  `docker compose up -d --scale ollama=0 --scale ollama-init=0`. The host's Ollama must listen on an address the containers can reach
  (not only `127.0.0.1`), for example `OLLAMA_HOST=0.0.0.0`. That exposes it on your network, so use a firewall. On Windows, Ollama bound to
  `127.0.0.1` is **not** reachable from containers.
* **GPU:** `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d` after installing the NVIDIA Container Toolkit; also set
  `stt.device: cuda`, `stt.compute_type: float16` and remove `num_gpu: 0` from `config/ai/settings.yaml`. Not tested.

## Data
Volumes: `media` (archives, results, temporary files), `pgdata`, `redisdata`, `models`, `ollama`, `logs`. They survive `down`, restarts and rebuilds. Only `down -v` removes them.

## Troubleshooting
| Problem | Fix |
|---|---|
| `exec /app/scripts/entrypoint.sh: no such file or directory` | CRLF line endings: `python scripts/normalize_eol.py`, rebuild. |
| `apt-get` or `pip` fails during build | Network/DNS problem. Run the build again (downloads are retried and cached). |
| `web` never becomes healthy | `docker compose logs migrate web`. Usually a missing or short `DJANGO_SECRET_KEY`, a bad `.env`, or a configuration error. |
| Jobs end as partial, `llm_unavailable` | `docker compose logs ollama ollama-init`; was the model downloaded? Then `docker compose exec worker python manage.py check_llm`, and `reprocess_job`. |
| Worker killed (exit 137) | Out of memory: give Docker more RAM, or use `model: small` in `config/ai/stt.yaml`. |
| `DisallowedHost` / CSRF error | Add the exact host (and `https://host`) to `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`. |
