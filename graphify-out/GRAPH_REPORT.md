# Graph Report - audio-intelligence  (2026-11-15)

## Corpus Check
- 124 files · ~42,964 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 10 file(s) not represented in the graph (top: (none) 4, .in 2, .example 1)

## Summary
- 1339 nodes · 3049 edges · 116 communities (80 shown, 36 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 243 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- archives.py
- renderer.py
- results_zip.py
- pytest
- storage.py
- test_api.py
- processing/tasks.py
- storage
- pipeline.py
- test_pipeline.py
- providers/base.py
- llm
- stt
- services/engine.py
- config.py
- notifications/services.py
- maintenance.py
- ResultSerializer
- Job
- labels
- RuntimeConfig
- output.py
- test_hardening.py
- views.py
- test_grounding.py
- JobStatusSerializer
- test_extraction.py
- services
- document
- environment
- api.py
- registry.py
- db
- web
- beat
- healthcheck
- resources
- worker
- extraction
- db
- x-app
- flatten
- fonts
- audio.py
- en
- transcript
- job.js
- upload.js
- SecurityHeadersMiddleware
- models.py
- pdf_template.yaml
- test_ollama_adapter_builds_request_from_configuration
- language
- processing_date
- entrypoint.sh
- transcription/engine.py
- Persian Audio Intelligence Platform
- test_archives.py
- uploads/services.py
- .edit_yaml
- access.py
- conftest.py
- builders.py
- test_real_models.py
- Technical decisions
- providers/base.py
- Setup guide: run the project on a new Windows machine
- Security Review
- CLAUDE.md
- Running with Docker — step by step (Windows + Docker Desktop)
- test_zip.py
- iter_extract
- api.py
- _extract_archive
- ollama
- _Closing
- settings/base.py
- 3. اجرا روی سرور ابری
- uploads
- 2. اجرای لوکال (ویندوز)
- راهنمای کامل راه‌اندازی از صفر: اجرای لوکال و روی سرور ابری
- processing/tasks.py
- email
- build_message
- Configuration
- check_llm.py
- processing
- email_retry
- extraction_retry
- retry
- Architecture

## God Nodes (most connected - your core abstractions)
1. `Job` - 57 edges
2. `get_config()` - 53 edges
3. `AudioFile` - 35 edges
4. `ConfigError` - 32 edges
5. `wav_bytes()` - 32 edges
6. `_upload()` - 27 edges
7. `ExtractionEngine` - 27 edges
8. `Findings` - 26 edges
9. `JobStatus` - 26 edges
10. `ArchiveValidationError` - 26 edges

## Surprising Connections (you probably didn't know these)
- `LLM: `config/ai/settings.yaml`` --references--> `LLMProvider`  [INFERRED]
  README.md → apps/information_extraction/providers/base.py
- `Findings` --references--> `test_console_backend_is_never_reported_as_a_delivered_email()`  [INFERRED]
  SECURITY.md → tests/test_hardening.py
- `Findings` --references--> `test_long_transcripts_are_cut_to_fit_the_context_window()`  [INFERRED]
  SECURITY.md → tests/test_hardening.py
- `Findings` --references--> `test_one_bad_file_does_not_stop_others_partial_completion()`  [INFERRED]
  SECURITY.md → tests/test_pipeline.py
- `Findings` --references--> `test_duplicate_email_is_prevented()`  [INFERRED]
  SECURITY.md → tests/test_pipeline.py

## Import Cycles
- None detected.

## Communities (116 total, 36 thin omitted)

### Community 0 - "archives.py"
Cohesion: 0.19
Nodes (14): ArchiveValidationError, ArchiveEntry, _check_ratio(), _classify(), configure_rarfile(), detect_archive_kind(), detect_rar_tool(), display_name_for() (+6 more)

### Community 1 - "renderer.py"
Cohesion: 0.06
Nodes (24): DocumentContext, _humanize(), _is_empty(), PdfRenderer, on_page(), _register_font(), _t(), BidiParagraph (+16 more)

### Community 2 - "results_zip.py"
Cohesion: 0.19
Nodes (5): verify_zip_signature(), build(), entry_name(), pdf_files(), test_entry_names_are_unique_safe_and_ordered()

### Community 3 - "pytest"
Cohesion: 0.30
Nodes (12): ConfigError, test_archive_retention_below_one_hour_is_rejected(), test_invalid_extraction_schema_is_rejected(), test_invalid_yaml_is_reported(), test_missing_prompt_file_is_actionable(), test_pdf_fields_must_exist_in_schema(), test_prompt_path_cannot_escape_config_dir(), test_schema_must_define_properties() (+4 more)

### Community 4 - "storage.py"
Cohesion: 0.21
Nodes (13): cleanup_job_work(), create_job_from_upload(), UploadResult, archive_dir(), atomic_write_bytes(), ensure_dir(), _ensure_dir(), _job_dir() (+5 more)

### Community 5 - "test_api.py"
Cohesion: 0.18
Nodes (18): Findings, api_upload(), auth(), upload_file(), client(), test_expired_signed_link(), test_invalid_email_rejected(), test_invalid_uploads_are_rejected() (+10 more)

### Community 6 - "processing/tasks.py"
Cohesion: 0.06
Nodes (9): DocumentGenerationConfig, InformationExtractionConfig, NotificationsConfig, send_job_email(), ProcessingConfig, TranscriptionConfig, UploadsConfig, WebConfig (+1 more)

### Community 7 - "storage"
Cohesion: 0.18
Nodes (11): backend, directory, retention_seconds, directory, retention_seconds, storage, archive, max_retention_seconds (+3 more)

### Community 8 - "pipeline.py"
Cohesion: 0.18
Nodes (21): get_config(), AudioFile, Meta, FileStatus, StageStatus, _finish_file(), _handle_file_error(), _inc() (+13 more)

### Community 9 - "test_pipeline.py"
Cohesion: 0.09
Nodes (31): send_job_email(), acquire(), leased(), release(), renew(), _ttl(), user_message(), results_abspath() (+23 more)

### Community 10 - "providers/base.py"
Cohesion: 0.18
Nodes (10): LLMProvider, LLMRequest, LLMRequestError, LLMResponse, OllamaProvider, OpenAICompatibleProvider, test_ollama_unreachable_is_transient(), test_overflowing_prompt_is_flagged_in_the_extraction_metadata() (+2 more)

### Community 11 - "llm"
Cohesion: 0.07
Nodes (29): ai, extraction, language, max_response_chars, max_transcript_chars, response_format, retry, additional_context (+21 more)

### Community 12 - "stt"
Cohesion: 0.08
Nodes (25): max_gap_seconds, max_sentences, channels, ffmpeg_binary, filters, sample_rate, stt, beam_size (+17 more)

### Community 13 - "services/engine.py"
Cohesion: 0.17
Nodes (10): ChatMessage, ExtractionEngine, describe_fields(), format_timestamps(), render(), sanitize_transcript(), schema_text(), test_long_transcripts_are_truncated() (+2 more)

### Community 14 - "config.py"
Cohesion: 0.15
Nodes (14): load_config(), _load_yaml(), _read_text(), _resolve_in(), resolve_project_path(), validate_extraction_schema(), _validate_provider(), _validate_shape() (+6 more)

### Community 15 - "notifications/services.py"
Cohesion: 0.19
Nodes (4): _handle_failure(), is_transient_smtp_error(), error_text(), counts()

### Community 16 - "maintenance.py"
Cohesion: 0.17
Nodes (15): enqueue(), enqueue_email(), enqueue_file(), enqueue_job(), _send(), _due(), _expire(), _lease_free() (+7 more)

### Community 17 - "ResultSerializer"
Cohesion: 0.20
Nodes (4): get_authorized_job(), JobResultsView, ResultSerializer, Meta

### Community 18 - "Job"
Cohesion: 0.16
Nodes (16): reload_config(), cleanup_storage(), Command, Job, Meta, progress(), archive_abspath(), _job() (+8 more)

### Community 19 - "labels"
Cohesion: 0.12
Nodes (16): en, fa, en, fa, en, fa, duration, filename (+8 more)

### Community 21 - "output.py"
Cohesion: 0.16
Nodes (9): ExtractionOutcome, _first_json_object(), parse_and_validate(), parse_json_object(), validate_against_schema(), ValidationOutcome, test_json_parsing_tolerates_wrapping(), test_validation_rejects_non_objects_and_oversized() (+1 more)

### Community 22 - "test_hardening.py"
Cohesion: 0.14
Nodes (16): _fake_urlopen(), test_console_backend_is_never_reported_as_a_delivered_email(), test_email_retries_survive_more_than_default_attempts(), test_extraction_and_email_have_longer_retry_windows_than_default(), test_llm_outage_longer_than_the_old_90_seconds_window_is_survived(), test_no_email_is_sent_while_extraction_retries_are_pending(), test_ollama_healthcheck_reports_missing_model_and_success(), test_partial_result_with_console_backend_carries_the_warning() (+8 more)

### Community 23 - "views.py"
Cohesion: 0.17
Nodes (3): _enforce_csrf(), index(), UiUploadView

### Community 24 - "test_grounding.py"
Cohesion: 0.07
Nodes (29): mask_email(), redact(), RedactingFilter, _allows_null(), _Evidence, ground(), walk(), _is_placeholder() (+21 more)

### Community 26 - "test_extraction.py"
Cohesion: 0.21
Nodes (11): LLMUnavailableError, InvalidLLMOutputError, AlternateProvider, FakeProvider, _extract(), test_llm_unavailable_propagates_as_transient(), test_model_is_selected_from_configuration(), test_output_violating_new_schema_is_rejected() (+3 more)

### Community 27 - "services"
Cohesion: 0.14
Nodes (13): command, image, restart, volumes, services, redis, volumes, logs (+5 more)

### Community 28 - "document"
Cohesion: 0.17
Nodes (12): document, author, language, margins_mm, page_size, subject, bottom, left (+4 more)

### Community 29 - "environment"
Cohesion: 0.48
Nodes (12): environment, CACHE_REDIS_URL, DB_ENGINE, DJANGO_SETTINGS_MODULE, LLM_BASE_URL, LOG_DIR, MEDIA_ROOT, POSTGRES_HOST (+4 more)

### Community 30 - "api.py"
Cohesion: 0.21
Nodes (6): verify_download_signature(), _error(), JobCreateView, JobResultsZipView, JobStatusView, ResultDownloadView

### Community 31 - "registry.py"
Cohesion: 0.24
Nodes (4): build_provider(), ProviderNotFound, resolve_provider_class(), test_builtin_provider_names_resolve()

### Community 32 - "db"
Cohesion: 0.36
Nodes (8): depends_on, condition, db, redis, condition, depends_on, depends_on, depends_on

### Community 33 - "web"
Cohesion: 0.18
Nodes (11): web, build, cap_drop, command, env_file, extra_hosts, image, ports (+3 more)

### Community 34 - "beat"
Cohesion: 0.20
Nodes (10): build, cap_drop, command, env_file, extra_hosts, image, restart, security_opt (+2 more)

### Community 35 - "healthcheck"
Cohesion: 0.39
Nodes (9): healthcheck, healthcheck, interval, retries, start_period, test, timeout, healthcheck (+1 more)

### Community 36 - "resources"
Cohesion: 0.25
Nodes (8): resources, deploy, devices, reservations, services, ollama, worker, deploy

### Community 37 - "worker"
Cohesion: 0.20
Nodes (10): worker, build, cap_drop, command, env_file, extra_hosts, image, restart (+2 more)

### Community 39 - "extraction"
Cohesion: 0.25
Nodes (8): extraction, fields, hide_empty, labels, unavailable_text, visible, en, fa

### Community 40 - "db"
Cohesion: 0.25
Nodes (8): environment, image, restart, volumes, POSTGRES_DB, POSTGRES_PASSWORD, POSTGRES_USER, db

### Community 41 - "x-app"
Cohesion: 0.22
Nodes (9): x-app, build, cap_drop, env_file, extra_hosts, image, restart, security_opt (+1 more)

### Community 42 - "flatten"
Cohesion: 0.52
Nodes (3): _empty(), flatten(), _inline()

### Community 43 - "fonts"
Cohesion: 0.29
Nodes (7): fonts, bold, heading_size, line_spacing, regular, size, title_size

### Community 44 - "audio.py"
Cohesion: 0.08
Nodes (16): AudioValidationError, AudioInfo, _decode_duration(), normalize(), _normalize_with_pyav(), probe(), validate_audio(), _edit_distance() (+8 more)

### Community 45 - "en"
Cohesion: 0.53
Nodes (6): title, title, title, en, fa, title

### Community 46 - "transcript"
Cohesion: 0.33
Nodes (6): en, fa, transcript, empty_text, show_timestamps, visible

### Community 47 - "job.js"
Cohesion: 0.60
Nodes (5): loadDownloads(), poll(), renderFiles(), showFinal(), update()

### Community 48 - "upload.js"
Cohesion: 0.60
Nodes (5): choose(), humanSize(), show(), validateEmail(), validateFile()

### Community 50 - "models.py"
Cohesion: 0.13
Nodes (4): Migration, Migration, LeaseMixin, Meta

### Community 51 - "pdf_template.yaml"
Cohesion: 0.40
Nodes (4): metadata, fields, visible, sections

### Community 53 - "language"
Cohesion: 0.67
Nodes (3): language, en, fa

### Community 54 - "processing_date"
Cohesion: 0.67
Nodes (3): processing_date, en, fa

### Community 71 - "transcription/engine.py"
Cohesion: 0.12
Nodes (7): api_exception_handler(), PermanentError, FasterWhisperEngine, finalize_result(), load_pcm16_wav(), TranscriptionEngine, TranscriptionResult

### Community 72 - "Persian Audio Intelligence Platform"
Cohesion: 0.14
Nodes (14): Docker, Email delivery, Environment configuration, Graphify workflow, Installation (local), Known limitations, Persian Audio Intelligence Platform, Prerequisites & hardware (+6 more)

### Community 73 - "test_archives.py"
Cohesion: 0.27
Nodes (17): inspect_archive(), is_unsafe_member_name(), wav_bytes(), zip_bytes(), test_archive_without_audio_is_rejected(), test_audio_magic_detection(), test_compression_bomb_ratio_is_rejected(), test_corrupt_zip_is_rejected() (+9 more)

### Community 74 - "uploads/services.py"
Cohesion: 0.24
Nodes (5): validate_upload_metadata(), archive_mime_allowed(), audio_matches_extension(), sniff_archive(), sniff_audio()

### Community 75 - ".edit_yaml"
Cohesion: 0.23
Nodes (8): ConfigEditor, test_backoff_is_exponential_and_capped(), test_check_llm_command_fails_loudly_when_the_service_is_down(), test_context_window_too_small_for_the_schema_is_a_clear_config_error(), test_long_transcripts_are_cut_to_fit_the_context_window(), test_retry_policy_falls_back_to_default_when_not_configured(), test_short_transcripts_are_sent_complete_and_timestamps_are_available_to_custom_prompts(), _tokens()

### Community 76 - "access.py"
Cohesion: 0.20
Nodes (9): can_access_job(), extract_token(), generate_token(), grant_session(), hash_token(), session_allows(), token_matches(), verify_job_link() (+1 more)

### Community 77 - "conftest.py"
Cohesion: 0.12
Nodes (5): CoreConfig, config_check(), app_config(), cfg(), FakeSTT

### Community 79 - "test_real_models.py"
Cohesion: 0.40
Nodes (3): get_engine(), test_faster_whisper_loads_and_transcribes(), test_ollama_extraction_returns_schema_valid_persian_json()

### Community 80 - "Technical decisions"
Cohesion: 0.40
Nodes (4): Decisions, Environment inspected (2026-11-14), Graphify, Technical decisions

### Community 82 - "Setup guide: run the project on a new Windows machine"
Cohesion: 0.12
Nodes (15): 0. Requirements, 10. Problems, 11. Optional: run the tests, 1. Get the project, 2. Create the Python environment, 3. Install the AI model (Ollama), 4. Create your local settings file, 5. Prepare the database and check everything (+7 more)

### Community 83 - "Security Review"
Cohesion: 0.50
Nodes (3): Residual risks and recommendations, Security Review, Tooling results (2026-11-14)

### Community 86 - "Running with Docker — step by step (Windows + Docker Desktop)"
Cohesion: 0.15
Nodes (12): 1. Start Docker Desktop, 2. Make sure Ollama runs on the host and has the model, 3. Create `.env`, 4. Build the image, 5. Start the stack, 6. Watch the processing, 7. Everyday commands, 8. Where the data lives (+4 more)

### Community 87 - "test_zip.py"
Cohesion: 0.27
Nodes (10): zip_name(), test_attach_format_pdf_keeps_separate_attachments(), test_email_has_one_zip_attachment_with_every_pdf(), test_failed_files_are_left_out_and_partial_results_still_zipped(), test_pdfs_in_the_zip_are_byte_identical_to_the_stored_results(), test_too_large_zip_is_replaced_by_a_signed_link_that_downloads_it(), test_zip_endpoint_requires_the_job_token_or_session(), test_zip_is_gone_after_result_retention_and_unavailable_without_pdfs() (+2 more)

### Community 89 - "iter_extract"
Cohesion: 0.17
Nodes (6): _copy_limited(), ExtractedFile, iter_extract(), _LimitExceeded, _member_stream(), limits()

### Community 91 - "_extract_archive"
Cohesion: 0.21
Nodes (10): PipelineError, TransientError, JobStage, _dispatch_pending_files(), _extract_archive(), _finish_without_files(), _retry_job_stage(), _run() (+2 more)

### Community 92 - "ollama"
Cohesion: 0.29
Nodes (7): OLLAMA_KEEP_ALIVE, environment, image, profiles, restart, volumes, ollama

### Community 94 - "settings/base.py"
Cohesion: 0.21
Nodes (4): env_bool(), env_int(), env_str(), _load_env_local()

### Community 97 - "3. اجرا روی سرور ابری"
Cohesion: 0.15
Nodes (13): 3.10 آزمایش نهایی روی سرور, 3.11 نگهداری, 3.12 گزینه‌ها, 3.1 انتخاب سرور, 3.2 دامنه و DNS, 3.3 آماده‌سازی سرور, 3.4 انتقال پروژه به سرور, 3.5 ساخت فایل `.env` روی سرور (+5 more)

### Community 98 - "uploads"
Cohesion: 0.18
Nodes (11): uploads, allowed_archive_extensions, allowed_audio_extensions, max_archive_bytes, max_audio_duration_seconds, max_compression_ratio, max_entries, max_extracted_bytes (+3 more)

### Community 99 - "2. اجرای لوکال (ویندوز)"
Cohesion: 0.18
Nodes (11): 2.10 (اختیاری) اجرای لوکال با Docker, 2.1 نصب برنامه‌های لازم, 2.2 دریافت پروژه, 2.3 ساخت محیط پایتون, 2.4 دانلود مدل زبانی, 2.5 فایل تنظیمات محلی, 2.6 آماده‌سازی و بررسی, 2.7 اجرا: سه پنجرهٔ PowerShell (+3 more)

### Community 100 - "راهنمای کامل راه‌اندازی از صفر: اجرای لوکال و روی سرور ابری"
Cohesion: 0.20
Nodes (8): 1. پروژه چیست و چگونه کار می‌کند, 4. تنظیم ایمیل, 5. تغییر مدل، فیلدهای استخراج، پرامپت و PDF, 6. آزمایش و راستی‌آزمایی, 7. عیب‌یابی, 8. محدودیت‌های شناخته‌شده, راهنمای کامل راه‌اندازی از صفر: اجرای لوکال و روی سرور ابری, فهرست

### Community 101 - "processing/tasks.py"
Cohesion: 0.36
Nodes (6): cleanup_job_work(), cleanup_storage(), finalize_job(), process_file(), recover_jobs(), run_job()

### Community 102 - "email"
Cohesion: 0.25
Nodes (8): attach_format, attach_pdfs, download_link_ttl_seconds, include_extracted_information, max_attachment_total_bytes, send_failure_notice, send_partial_results, email

### Community 104 - "build_message"
Cohesion: 0.33
Nodes (6): build_message(), sign_download(), sign_job_link(), sign_zip(), test_a_signature_for_one_job_does_not_open_another_jobs_zip(), test_results_endpoint_and_status_page_offer_the_zip()

### Community 105 - "Configuration"
Cohesion: 0.33
Nodes (6): Configuration, Extraction schema: `config/ai/extraction_schema.json`, LLM: `config/ai/settings.yaml`, PDF: `config/ai/pdf_template.yaml`, Prompts: `config/ai/prompts/*.txt`, Whisper: `config/ai/stt.yaml`

### Community 107 - "processing"
Cohesion: 0.40
Nodes (4): notifications, processing, lease_seconds, stale_after_seconds

### Community 108 - "email_retry"
Cohesion: 0.40
Nodes (5): backoff_multiplier, initial_delay_seconds, max_attempts, max_delay_seconds, email_retry

### Community 109 - "extraction_retry"
Cohesion: 0.40
Nodes (5): backoff_multiplier, initial_delay_seconds, max_attempts, max_delay_seconds, extraction_retry

### Community 110 - "retry"
Cohesion: 0.40
Nodes (5): retry, backoff_multiplier, initial_delay_seconds, max_attempts, max_delay_seconds

### Community 111 - "Architecture"
Cohesion: 0.67
Nodes (3): Architecture, Django application components, Processing flow

## Knowledge Gaps
- **36 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_config()` connect `pipeline.py` to `renderer.py`, `storage.py`, `processing/tasks.py`, `test_pipeline.py`, `config.py`, `notifications/services.py`, `maintenance.py`, `Job`, `RuntimeConfig`, `output.py`, `views.py`, `test_extraction.py`, `registry.py`, `audio.py`, `uploads/services.py`, `conftest.py`, `test_real_models.py`, `_extract_archive`, `build_message`, `check_llm.py`?**
  _High betweenness centrality (0.069) - this node is a cross-community bridge._
- **Are the 30 inferred relationships involving `Job` (e.g. with `cleanup_job_work()` and `cleanup_storage()`) actually correct?**
  _`Job` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Should `renderer.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06237424547283702 - nodes in this community are weakly interconnected._
- **Why does `LLMProvider` connect `providers/base.py` to `Configuration`, `services/engine.py`, `providers/base.py`, `output.py`, `test_extraction.py`, `registry.py`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **Are the 18 inferred relationships involving `AudioFile` (e.g. with `_extract_archive()` and `_finish_file()`) actually correct?**
  _`AudioFile` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Should `processing/tasks.py` be split into smaller, more focused modules?**
  _Cohesion score 0.05714285714285714 - nodes in this community are weakly interconnected._
- **Why does `LLM: `config/ai/settings.yaml`` connect `Configuration` to `providers/base.py`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._