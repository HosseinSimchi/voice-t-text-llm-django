# Security Review

This is an engineering self-review carried out during development. It is **not** a formal audit or certification.
Severity uses Critical / High / Medium / Low / Info. "Verified" means an automated test or tool run in this
repository confirms the mitigation; the evidence is named in each row.

## Tooling results (2026-11-14)

| Tool | Result |
|---|---|
| `pytest` (default suite) | 162 passed, 3 skipped (integration tests, run separately) |
| `python manage.py check --deploy --settings=config.settings.prod` | No security errors. Warning `security.W021` (HSTS preload is opt-in by design); local-only `audio.W001/W002` (FFmpeg/RAR tool absent on the Windows dev host) |
| `pip-audit -r requirements.txt` | First run: **5 known vulnerabilities in djangorestframework 3.16.1** → upgraded to 3.18.3 → **"No known vulnerabilities found"** |

## Findings

| # | Finding | Severity | Affected component | Mitigation | Verification |
|---|---|---|---|---|---|
| 1 | Zip Slip / path traversal through archive member names | Critical | `apps/uploads/archives.py` | Member names are never used as paths. Files are written as `<index>.<ext>` in a per-job directory. Entries with `..`, absolute paths, drive letters or NUL bytes reject the **whole** archive. `safe_join` guards every storage path. | Verified: `test_path_traversal_names_are_detected`, `test_zip_slip_archive_is_rejected`, `test_rar_traversal_is_rejected`, `test_invalid_uploads_are_rejected[...traversal]` |
| 2 | Decompression bombs / resource exhaustion | High | archives, upload | Declared-size and per-entry ratio checks at upload. Byte limits enforced **while streaming** (headers can lie). Limits on archive size, files, entries, per-file and total size, and audio duration. | Verified: `test_compression_bomb_ratio_is_rejected`, `test_streaming_limits_are_enforced_regardless_of_headers`, `test_too_many_files`, `test_oversized_archive_rejected` |
| 3 | Symlinks, devices, encrypted entries, nested archives | High | archives | Reported as unsupported and never extracted. Password-protected RAR archives are rejected. | Verified: `test_unsupported_entries_are_reported_not_fatal` |
| 4 | Unsafe RAR extraction | High | `rarfile` backend | `rarfile` streams entry data from the tool's stdout (`unrar p` / `7z -so`), so the external tool never writes to the filesystem itself. The same name and size rules apply. | Partially verified: stored RAR tested; compressed RAR via `7zip` not tested (no RAR tool on the dev host) |
| 5 | Spoofed file types (extension/MIME) | Medium | `sniffing.py`, `audio.py` | Extension allow-list, MIME allow-list, magic-byte check that must match the extension, then FFmpeg/PyAV must demux a real audio stream. | Verified: `test_audio_magic_detection`, `test_invalid_uploads_are_rejected[...]`, `test_one_bad_file_does_not_stop_others_partial_completion` |
| 6 | IDOR on jobs, results and downloads | High | `processing/api.py`, `access.py` | 256-bit random token (only the SHA-256 is stored, compared in constant time), session grants for browsers, signed time-limited email links. Unauthorised requests get **404** so ids cannot be enumerated. UUIDv4 ids. | Verified: `test_status_requires_token_and_hides_existence`, `test_token_of_one_job_cannot_read_another`, `test_signed_download_link`, `test_expired_signed_link` |
| 7 | CSRF on the browser upload | Medium | `apps/web/views.py` | The UI uses its own CSRF-enforced endpoint. The token API is stateless and grants no session. | Verified: `test_ui_upload_requires_csrf_and_grants_session` |
| 8 | XSS in the UI | Medium | templates, `job.js` | Django autoescaping. JS writes user data only through `textContent`. Strict CSP (`script-src 'self'`, no inline script), with data passed via `json_script`. | Verified: CSP header in `test_security_headers`; manual browser check |
| 9 | Prompt injection through transcripts | Medium | `information_extraction/services/prompts.py` | Transcript is delimited data. Delimiter look-alikes and control characters are stripped. Single-pass templating, so `{{…}}` in a transcript is never expanded. The system prompt forbids following transcript instructions. The output must pass JSON Schema validation and size limits. | Verified: `test_transcript_cannot_break_out_of_its_data_block`. Residual risk: a model may still be steered into wrong *content* within the schema. |
| 10 | Untrusted LLM output | Medium | `validators/output.py` | Response size cap (`max_response_chars`), JSON object only, Draft 2020-12 validation with `additionalProperties: false` and `maxLength`/`maxItems`. Invalid output is never stored. | Verified: `test_validation_rejects_non_objects_and_oversized`, `test_output_violating_new_schema_is_rejected` |
| 11 | Data sent to external AI services | Medium | provider registry | Default provider is local Ollama. Others only when explicitly configured. API keys only via the env var named in `api_key_env`. | Verified by configuration review |
| 12 | Email header injection | Medium | upload serializer, notifications | `EmailField` validation, CR/LF rejected, Django mail API with a fixed recipient list. | Verified: `test_invalid_email_rejected` |
| 13 | Abuse / flooding | Medium | DRF throttling | Scoped rate limits for uploads, status and downloads. | Configured. Effective across processes only with a Redis cache (`CACHE_REDIS_URL`), which docker-compose sets. |
| 14 | Secrets in code or images | High | settings, Docker | All secrets come from the environment. Production refuses a missing or short `DJANGO_SECRET_KEY`. `.env` is git- and docker-ignored. No secrets in the image. | Verified: `check --deploy` run; file review |
| 15 | Sensitive data in logs | Low | `core/logging.py` | Redacting filter masks emails and token/sig/password values. Transcripts are not logged. | Verified: `test_logging_redacts_emails_and_tokens` |
| 16 | Container privileges | Medium | Dockerfile, compose | Non-root user (uid 10001), `no-new-privileges`, `cap_drop: ALL`. Ollama, Redis and Postgres are not published to the host. | Not verified at runtime (Docker image not built on the dev host) |
| 17 | Filesystem permissions | Low | storage | Files `0640`, directories `0750`, exclusive create (`O_EXCL`), atomic replace, and media never served directly. | Verified on POSIX semantics by review; Windows ignores modes |
| 18 | Production HTTP hardening | Medium | `settings/prod.py` | HSTS, SSL redirect, secure cookies, `X-Frame-Options: DENY`, nosniff, referrer policy, CSP. | Verified: `check --deploy` |
| 19 | Vulnerable dependency (DRF 3.16.1) | High | `requirements.txt` | Upgraded to djangorestframework 3.18.3. | Verified: `pip-audit` clean after the upgrade |
| 20 | Duplicate email after a crash between SMTP acceptance and the DB write | Low | notifications | Lease plus `email_status`. Stable `Message-ID` for de-duplication. Documented as a residual risk. | Verified: `test_duplicate_email_is_prevented` (normal path) |
| 22 | Misleading delivery status: console e-mail backend reported as "sent" | Medium | notifications, `status.py` | `email_transport` is recorded per job; anything other than SMTP shows an explicit "no real e-mail was sent" message instead of the success text; start-up warning `audio.W003`. | Verified: `test_console_backend_is_never_reported_as_a_delivered_email`, real SMTP round-trip tests |
| 23 | Hallucinated / placeholder values in LLM output | Medium | `services/grounding.py` | Schema-driven `x-grounded` check against the transcript plus a configurable placeholder list; removed values are recorded in `extraction_meta.ungrounded_removed`. | Verified: `tests/test_grounding.py`; run on real model output |
| 24 | Silent prompt truncation by the model (instructions dropped) | Low | `services/engine.py` | Token-aware transcript budget; `context_overflow_suspected` recorded. | Verified: `test_long_transcripts_are_cut_to_fit_the_context_window` |
| 21 | Swagger UI loads assets from a CDN | Info | `/api/docs/` | The relaxed CSP applies only under `/api/docs`. Disable that route in production if not needed. | Review |

## Residual risks and recommendations

* Put the app behind a TLS-terminating reverse proxy; set `DJANGO_BEHIND_PROXY=true`.
* Run `pip-audit` in CI and rebuild images regularly (FFmpeg/7zip parsers are a large attack surface; keep the worker container isolated).
* For untrusted public deployments, consider running the worker with a read-only root filesystem and seccomp profile, and add antivirus scanning of archives.
* SMTP acceptance does not prove inbox delivery.
