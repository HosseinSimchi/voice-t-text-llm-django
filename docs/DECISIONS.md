# Technical decisions

## Environment inspected (2026-11-14)
* CPU Intel i7-8550U (4 cores / 8 threads), 7.4 GB RAM, Intel UHD 620 + AMD Radeon 530 (no CUDA), 305 GB free disk, Windows 11.
* Python 3.12.2, uv 0.13.7, Node.js (for the Tailwind build), Ollama installed, Docker CLI present but the engine was not running.
* No FFmpeg, unrar/7z or Redis on the host.
* Network: `files.pythonhosted.org` resolved only intermittently; a long retry loop eventually installed every package from official PyPI.

## Decisions
| Decision | Why |
|---|---|
| Whisper `medium`, `int8`, CPU | `small` was the first default, but on real Persian clips it gave WER 46 % vs 30 % for `medium` (garbled words such as «اازمون», «گوزارش»). `medium` needs ~2 GB RAM and runs at ~2-2.5× audio duration. Configurable from `tiny` to `large-v3`. |
| `qwen2.5:3b` via Ollama, `num_gpu: 0` | Multilingual and handles Persian at about 2 GB. Partial offload to the iGPU produced garbage tokens (`@@@@`) and HTTP 500 on this machine, so the default is CPU-only. |
| Samples passed to Whisper instead of a file path | faster-whisper 1.2.1 calls `av.open(metadata_errors=…)`, which PyAV 19 removed. The pipeline already produces 16 kHz mono PCM, so it reads that WAV and passes samples. |
| Transcript PDF first, final PDF after extraction | Keeps the spec's order (PDF before LLM) and guarantees a PDF survives an LLM failure, while the final PDF still contains the extraction. |
| Database leases instead of Celery locks | Atomic conditional UPDATE works on SQLite and PostgreSQL and survives broker loss. |
| Stage and attempt counters in the DB, backoff scheduled with `countdown` | Recovery works even if Redis loses the delayed message (`next_attempt_at`). |
| PostgreSQL in Docker, SQLite locally | Concurrent workers need a real database. SQLite keeps local setup simple. |
| Custom RTL line breaker plus python-bidi | ReportLab lacks full bidi support. Breaking lines before reordering keeps multi-line paragraphs in the right order. |
| Tailwind built once with the standalone CLI, CSS committed | No CDN (a strict CSP stays possible) and no Node at runtime. |
| Vazirmatn bundled (SIL OFL 1.1) | Persian glyphs on every platform. Licence in `static/fonts/Vazirmatn-OFL.txt`. |
| Kombu filesystem broker for development | Lets you run a real async worker without Redis (`CELERY_FILESYSTEM_BROKER_DIR`). Not for production. |
| 404 for unauthorised access | Prevents probing for job and result ids (IDOR oracle). |

## Graphify
`graphifyy` 0.9.108 was installed in the virtualenv. `graphify update .` built `graphify-out/` (1076 nodes, 2581 edges, 71 communities; AST-only, no LLM).
`graphify claude install` added the rules to `CLAUDE.md` and hooks to `.claude/settings.json`. Rebuild after changes with `graphify update .`.
Semantic (LLM) enrichment of docs was not run: it needs an API key or an Ollama backend, and the AST graph covers the code.
