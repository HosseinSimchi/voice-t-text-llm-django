"""Regression tests for the LLM-outage, context-budget and e-mail-transparency fixes."""

import asyncio
import email
import io
import json
import threading
from email import policy

import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.test import APIClient

from apps.core.config import ConfigError
from apps.information_extraction.providers.base import ChatMessage, LLMRequest, LLMUnavailableError
from apps.information_extraction.providers.ollama import OllamaProvider
from apps.information_extraction.services.engine import ExtractionEngine
from apps.processing.messages import SUCCESS_MESSAGE_FA
from apps.processing.models import EmailStatus, FileStatus, Job, JobStatus, StageStatus
from apps.processing.status import user_message
from tests.builders import wav_bytes, zip_bytes
from tests.fakes import FakeProvider, FakeSTT
from tests.helpers import api_upload

pytestmark = pytest.mark.django_db(transaction=True)


def _upload(entries=None):
    body = api_upload(APIClient(), zip_bytes(entries or {"a.wav": wav_bytes(1.0)})).json()
    return Job.objects.get(pk=body["job_id"])


# ---------------------------------------------------------------- retry windows
def test_extraction_and_email_have_longer_retry_windows_than_default():
    from apps.core.config import load_config
    from tests.conftest import REAL_CONFIG

    cfg = load_config(REAL_CONFIG)  # the shipped configuration (the test fixture zeroes delays)
    assert cfg.retry_for("extraction")["max_attempts"] > cfg.retry_for("default")["max_attempts"]
    assert cfg.retry_for("email")["max_attempts"] > cfg.retry_for("default")["max_attempts"]
    for kind in ("extraction", "email"):
        window = sum(cfg.backoff_delay(n, kind) for n in range(1, cfg.retry_for(kind)["max_attempts"]))
        assert 10 * 60 <= window < cfg.storage["archive"]["retention_seconds"], (kind, window)


def test_retry_policy_falls_back_to_default_when_not_configured(app_config):
    def drop(d):
        d["processing"].pop("extraction_retry")
        d["processing"].pop("email_retry")

    app_config.edit_yaml("app.yaml", drop)
    cfg = app_config.reload()
    assert cfg.retry_for("extraction") == cfg.retry_policy == cfg.retry_for("email")


def test_llm_outage_longer_than_the_old_90_seconds_window_is_survived():
    FakeProvider.unavailable_times = 5  # more failures than the default 3 attempts
    job = _upload()
    f = job.files.get()
    assert f.status == FileStatus.COMPLETED and f.extraction_status == StageStatus.DONE
    assert len(FakeSTT.calls) == 1  # transcription was never repeated
    assert job.status == JobStatus.COMPLETED and len(mail.outbox) == 1  # e-mail only after extraction finished


def test_no_email_is_sent_while_extraction_retries_are_pending(monkeypatch):
    monkeypatch.setattr("apps.processing.dispatch.enqueue_file", lambda *a, **k: None)  # retry is scheduled, not run
    FakeProvider.unavailable_times = 99
    job = _upload()
    job.refresh_from_db()
    f = job.files.get()
    assert f.status == FileStatus.PENDING and job.status != JobStatus.COMPLETED
    assert mail.outbox == []


def test_email_retries_survive_more_than_default_attempts(monkeypatch):
    import smtplib

    from django.core.mail.backends.locmem import EmailBackend

    original, state = EmailBackend.send_messages, {"fail": 4}

    def flaky(self, messages):
        if state["fail"]:
            state["fail"] -= 1
            raise smtplib.SMTPServerDisconnected("down")
        return original(self, messages)

    monkeypatch.setattr(EmailBackend, "send_messages", flaky)
    job = _upload()
    assert job.status == JobStatus.COMPLETED and job.email_attempts == 5 and len(mail.outbox) == 1
    assert len(FakeSTT.calls) == 1 and len(FakeProvider.requests) == 1


# ---------------------------------------------------------------- reprocess
def test_reprocess_extraction_only_keeps_transcripts_and_sends_a_new_email():
    FakeProvider.unavailable_times = 99
    job = _upload()
    f = job.files.get()
    assert f.extraction_status == StageStatus.FAILED and job.status == JobStatus.PARTIALLY_COMPLETED
    stt_calls = len(FakeSTT.calls)

    FakeProvider.unavailable_times = 0  # the LLM is back
    call_command("reprocess_job", str(job.id), stdout=io.StringIO())
    job.refresh_from_db()
    f.refresh_from_db()
    assert job.status == JobStatus.COMPLETED and f.status == FileStatus.COMPLETED
    assert f.extraction_status == StageStatus.DONE and f.pdf_includes_extraction
    assert len(FakeSTT.calls) == stt_calls  # transcription not repeated
    assert len(mail.outbox) == 2  # the incomplete report and the corrected one


def test_reprocess_refuses_unfinished_jobs_and_missing_archives(monkeypatch):
    monkeypatch.setattr("apps.processing.dispatch.enqueue_job", lambda *a, **k: None)
    job = _upload()
    with pytest.raises(CommandError, match="only finished jobs"):
        call_command("reprocess_job", str(job.id))
    monkeypatch.undo()
    job = _upload()
    with pytest.raises(CommandError, match="No file has a failed extraction"):
        call_command("reprocess_job", str(job.id))
    Job.objects.filter(pk=job.pk).update(archive_deleted_at=job.uploaded_at)
    with pytest.raises(CommandError, match="no longer stored"):
        call_command("reprocess_job", str(job.id), "--all")


def test_reprocess_all_restarts_from_the_retained_archive():
    job = _upload()
    old_file_id = job.files.get().id
    call_command("reprocess_job", str(job.id), "--all", stdout=io.StringIO())
    job.refresh_from_db()
    assert job.status == JobStatus.COMPLETED
    assert job.files.get().id != old_file_id and len(FakeSTT.calls) == 2


# ---------------------------------------------------------------- honest e-mail reporting
def test_console_backend_is_never_reported_as_a_delivered_email(settings):
    settings.EMAIL_REAL_DELIVERY = False
    settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    job = _upload()
    assert job.status == JobStatus.COMPLETED and job.email_status == EmailStatus.SENT
    assert job.email_transport == "console"
    message = user_message(job)
    assert message["kind"] == "success_local" and message["text"] != SUCCESS_MESSAGE_FA
    assert "SMTP" in message["text"]


def test_partial_result_with_console_backend_carries_the_warning(settings):
    settings.EMAIL_REAL_DELIVERY = False
    settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    FakeProvider.unavailable_times = 99
    message = user_message(_upload())
    assert message["kind"] == "partial" and "SMTP" in message["text"]


def test_smtp_transport_is_recorded_and_status_api_exposes_it():
    job = _upload()
    assert job.email_transport == "smtp" and user_message(job)["text"] == SUCCESS_MESSAGE_FA


# ---------------------------------------------------------------- real SMTP round-trip
@pytest.fixture
def smtp_sink(tmp_path, settings):
    from scripts.smtp_sink import handle

    state = {"count": 0, "fail_first": 0}
    out = tmp_path / "sink"
    out.mkdir()
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    box = {}

    async def start():
        server = await asyncio.start_server(lambda r, w: handle(r, w, out, state), "127.0.0.1", 0)
        box["port"] = server.sockets[0].getsockname()[1]
        box["server"] = server
        ready.set()

    thread = threading.Thread(target=lambda: (loop.run_until_complete(start()), loop.run_forever()), daemon=True)
    thread.start()
    assert ready.wait(10)
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    settings.EMAIL_HOST, settings.EMAIL_PORT = "127.0.0.1", box["port"]
    settings.EMAIL_USE_TLS = settings.EMAIL_USE_SSL = False
    settings.EMAIL_HOST_USER = settings.EMAIL_HOST_PASSWORD = ""
    settings.EMAIL_REAL_DELIVERY = True
    yield state, out

    async def shutdown():
        box["server"].close()
        await box["server"].wait_closed()
        for task in asyncio.all_tasks() - {asyncio.current_task()}:
            task.cancel()
        await asyncio.sleep(0)

    asyncio.run_coroutine_threadsafe(shutdown(), loop).result(10)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(10)
    loop.close()


def test_result_email_goes_through_a_real_smtp_connection(smtp_sink):
    state, out = smtp_sink
    job = _upload({"جلسه.wav": wav_bytes(1.0), "دوم.wav": wav_bytes(1.0)})
    assert job.status == JobStatus.COMPLETED and job.email_transport == "smtp"
    emls = list(out.glob("*.eml"))
    assert len(emls) == 1 and state["count"] == 1
    msg = email.message_from_bytes(emls[0].read_bytes(), policy=policy.default)
    assert msg["To"] == "user@example.com" and str(job.id) in msg.get_body(("plain",)).get_content()
    attachments = list(msg.iter_attachments())
    assert [a.get_content_type() for a in attachments] == ["application/zip"]
    import zipfile

    with zipfile.ZipFile(io.BytesIO(attachments[0].get_content())) as zf:  # decoded from the real SMTP message
        assert len(zf.namelist()) == 2 and all(zf.read(n).startswith(b"%PDF") for n in zf.namelist())
    assert "main_topic" not in msg.as_string()  # field values, not raw keys, are rendered


def test_temporary_smtp_rejection_is_retried_without_duplicates_or_repeated_stages(smtp_sink):
    state, out = smtp_sink
    state["fail_first"] = 2  # two 451 "try again later" answers
    job = _upload()
    assert job.status == JobStatus.COMPLETED and job.email_attempts == 3
    assert len(list(out.glob("*.eml"))) == 1  # exactly one message was accepted
    assert len(FakeSTT.calls) == 1 and len(FakeProvider.requests) == 1


def test_unreachable_smtp_server_ends_in_failed_email_but_keeps_results(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    settings.EMAIL_HOST, settings.EMAIL_PORT, settings.EMAIL_TIMEOUT = "127.0.0.1", 9, 2
    settings.EMAIL_USE_TLS = False
    job = _upload()
    assert job.email_status == EmailStatus.FAILED and job.status == JobStatus.FAILED
    assert job.error_code == "email_delivery_failed" and job.email_attempts == 6
    assert job.files.get().has_pdf  # PDFs survive an e-mail failure
    assert "@" not in job.email_last_error  # the stored error never contains addresses


# ---------------------------------------------------------------- LLM context budget & preflight
def _tokens(engine, messages):
    return sum(engine._estimate_tokens(m.content) for m in messages)


def test_long_transcripts_are_cut_to_fit_the_context_window(app_config):
    app_config.edit_yaml("ai/settings.yaml", lambda d: d["ai"].update(max_transcript_chars=1_000_000))
    cfg = app_config.reload()
    engine = ExtractionEngine(cfg)
    messages, truncated = engine.build_messages(transcript="کلمه " * 20000, filename="a.mp3",
                                                segments=[{"start": 0, "end": 5, "text": "کلمه " * 100}])
    window = cfg.llm["max_context_length"] - cfg.llm["max_output_tokens"]
    assert truncated is True
    assert _tokens(engine, messages) <= window  # the instructions can never be pushed out of the window


def test_short_transcripts_are_sent_complete_and_timestamps_are_available_to_custom_prompts(app_config):
    app_config.write_text("ai/prompts/extraction_prompt.txt",
                          "{{ field_descriptions }}\nTS:\n{{ timestamps }}\n<<<TRANSCRIPT_START>>>\n{{ transcript }}")
    engine = ExtractionEngine(app_config.reload())
    text = "سلام به همه. جلسه امروز درباره پروژه است. " * 5
    messages, truncated = engine.build_messages(transcript=text, filename="a.mp3",
                                                segments=[{"start": 0, "end": 5, "text": "سلام به همه."}])
    user = messages[1].content
    assert truncated is False and text.strip() in user and "[00:00-00:05]" in user


def test_default_prompt_is_compact_and_does_not_repeat_the_schema_or_the_transcript(cfg):
    messages, _ = ExtractionEngine(cfg).build_messages(
        transcript="سلام", filename="a.mp3", segments=[{"start": 0, "end": 5, "text": "سلام"}])
    total = sum(len(m.content) for m in messages)
    assert "additionalProperties" not in messages[1].content  # no raw JSON Schema (enforced via the provider)
    assert messages[1].content.count("سلام") == 1  # transcript appears once, not again as a timestamp block
    assert total < 3500, total  # the fixed prompt must stay small so CPU inference stays fast


def test_context_window_too_small_for_the_schema_is_a_clear_config_error(app_config):
    app_config.edit_yaml("ai/settings.yaml", lambda d: d["llm"].update(max_context_length=2500, max_output_tokens=2048))
    with pytest.raises(ConfigError, match="max_context_length"):
        ExtractionEngine(app_config.reload()).build_messages(transcript="x", filename="a", segments=[])


def test_overflowing_prompt_is_flagged_in_the_extraction_metadata(cfg, monkeypatch):
    from apps.information_extraction.providers.base import LLMResponse

    original = FakeProvider.complete

    def complete(self, request):
        resp = original(self, request)
        return LLMResponse(resp.content, resp.model, {"prompt_eval_count": cfg.llm["max_context_length"], "eval_count": 7})

    monkeypatch.setattr(FakeProvider, "complete", complete)
    outcome = ExtractionEngine(cfg).extract(transcript="سلام", filename="a", segments=[])
    assert outcome.meta["context_overflow_suspected"] is True and outcome.meta["output_tokens"] == 7


def _fake_urlopen(payload):
    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    return lambda req, timeout: Resp(json.dumps(payload).encode())


def test_ollama_healthcheck_reports_missing_model_and_success(cfg, monkeypatch):
    llm = {**cfg.llm, "provider": "ollama", "model": "qwen2.5:3b"}
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen({"models": [{"name": "llama3:8b", "model": "llama3:8b"}]}))
    ok, message = OllamaProvider(llm).healthcheck()
    assert not ok and "ollama pull qwen2.5:3b" in message and "llama3:8b" in message
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen({"models": [{"name": "qwen2.5:3b", "model": "qwen2.5:3b"}]}))
    assert OllamaProvider(llm).healthcheck()[0] is True


def test_unreachable_llm_error_names_the_host_and_reason_but_not_the_prompt(cfg):
    llm = {**cfg.llm, "provider": "ollama", "base_url": "http://127.0.0.1:9", "timeout": 3}
    with pytest.raises(LLMUnavailableError) as exc:
        OllamaProvider(llm).complete(LLMRequest([ChatMessage("user", "SECRET TRANSCRIPT TEXT")]))
    text = str(exc.value)
    assert "127.0.0.1:9" in text and "SECRET" not in text and "/api/chat" not in text
    ok, message = OllamaProvider(llm).healthcheck()
    assert ok is False and "127.0.0.1:9" in message


def test_check_llm_command_fails_loudly_when_the_service_is_down(app_config):
    app_config.edit_yaml("ai/settings.yaml", lambda d: d["llm"].update(
        provider="ollama", base_url="http://127.0.0.1:9", timeout=3))
    with pytest.raises(CommandError, match="unreachable"):
        call_command("check_llm", stdout=io.StringIO())


# ---------------------------------------------------------------- send_test_email command
def test_send_test_email_refuses_a_backend_that_does_not_deliver(settings):
    settings.EMAIL_REAL_DELIVERY = False
    settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    with pytest.raises(CommandError, match="not sent to anyone"):
        call_command("send_test_email", "a@example.com", stdout=io.StringIO())


def test_send_test_email_validates_the_address():
    with pytest.raises(CommandError, match="not a valid"):
        call_command("send_test_email", "not-an-address", stdout=io.StringIO())


def test_send_test_email_goes_through_smtp_and_never_prints_the_password(smtp_sink, settings):
    state, out = smtp_sink
    settings.EMAIL_HOST_USER = ""
    stdout = io.StringIO()
    call_command("send_test_email", "someone@example.com", stdout=stdout)
    assert state["count"] == 1 and "Accepted by the SMTP server" in stdout.getvalue()
    msg = email.message_from_bytes(next(out.glob("*.eml")).read_bytes(), policy=policy.default)
    assert msg["To"] == "someone@example.com" and "SMTP test" in msg["Subject"]


def test_send_test_email_can_resend_a_finished_jobs_real_result_with_the_zip(smtp_sink):
    state, out = smtp_sink
    job = _upload({"a.wav": wav_bytes(1.0), "b.wav": wav_bytes(1.0)})
    sent_before = state["count"]
    stdout = io.StringIO()
    call_command("send_test_email", "other@example.com", "--job", "latest", stdout=stdout)
    assert state["count"] == sent_before + 1 and "results-" in stdout.getvalue()
    newest = max(out.glob("*.eml"), key=lambda p: p.stat().st_mtime_ns)
    msg = email.message_from_bytes(newest.read_bytes(), policy=policy.default)
    assert msg["To"] == "other@example.com" and str(job.id) in msg.get_body(("plain",)).get_content()
    zips = [a for a in msg.iter_attachments() if a.get_content_type() == "application/zip"]
    assert len(zips) == 1
    job.refresh_from_db()
    assert job.email_attempts == 1  # re-sending never changes the job's own delivery state


def test_send_test_email_reports_a_smtp_failure_readably(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    settings.EMAIL_HOST, settings.EMAIL_PORT, settings.EMAIL_TIMEOUT = "127.0.0.1", 9, 2
    settings.EMAIL_REAL_DELIVERY, settings.EMAIL_USE_TLS = True, False
    with pytest.raises(CommandError, match="did not accept the message"):
        call_command("send_test_email", "a@example.com", stdout=io.StringIO())
