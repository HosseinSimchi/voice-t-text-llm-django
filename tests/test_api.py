from datetime import timedelta

import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.processing import access
from apps.processing.models import AudioFile, Job, JobStatus
from apps.uploads import storage
from tests.builders import rar_bytes, wav_bytes, zip_bytes
from tests.helpers import api_upload, auth, upload_file

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def client():
    return APIClient()


def test_zip_upload_returns_202_and_persists_archive(client, cfg):
    resp = api_upload(client)
    assert resp.status_code == 202, resp.content
    body = resp.json()
    assert body["status"] == "queued"
    assert body["message"] == "Your files have been accepted for processing."
    job = Job.objects.get(pk=body["job_id"])
    path = storage.archive_abspath(job.archive_path)
    assert path.is_file() and path.parent.name == str(job.id)
    assert path.name == "archive.zip"  # server-generated name
    assert job.archive_retain_until - job.uploaded_at >= timedelta(seconds=3600)
    assert job.access_token_hash != body["access_token"]  # only the hash is stored
    assert job.email == "user@example.com"


def test_rar_upload_is_accepted(client):
    resp = api_upload(client, rar_bytes({"a.wav": wav_bytes(0.5)}), name="audio.rar",
                      content_type="application/vnd.rar")
    assert resp.status_code == 202, resp.content
    job = Job.objects.get(pk=resp.json()["job_id"])
    assert job.archive_format == "rar"
    assert job.status == JobStatus.COMPLETED  # eager pipeline in tests


@pytest.mark.parametrize("name,data,ctype,code", [
    ("a.txt", b"hello", "text/plain", "unsupported_archive_type"),
    ("a.zip", b"not a zip at all", "application/zip", "invalid_archive_format"),
    ("a.zip", rar_bytes({"a.wav": wav_bytes(0.1)}), "application/zip", "invalid_archive_format"),
    ("a.zip", zip_bytes({"x.wav": wav_bytes(0.1)}), "text/html", "invalid_mime_type"),
    ("a.zip", zip_bytes({"readme.txt": b"x"}), "application/zip", "no_supported_audio"),
    ("a.zip", zip_bytes({"../../x.wav": wav_bytes(0.1)}), "application/zip", "archive_path_traversal"),
])
def test_invalid_uploads_are_rejected(client, name, data, ctype, code):
    resp = api_upload(client, data, name=name, content_type=ctype)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == code
    assert Job.objects.count() == 0


def test_invalid_email_rejected(client):
    resp = api_upload(client, email="not-an-email")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"


def test_oversized_archive_rejected(client, app_config):
    app_config.edit_yaml("app.yaml", lambda d: d["uploads"].update(max_archive_bytes=100))
    resp = api_upload(client)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "archive_too_large"


def test_status_requires_token_and_hides_existence(client):
    body = api_upload(client).json()
    url = f"/api/v1/jobs/{body['job_id']}/"
    assert client.get(url).status_code == 404
    assert client.get(url, **auth("wrong-token")).status_code == 404
    assert client.get("/api/v1/jobs/not-a-uuid/", **auth(body["access_token"])).status_code == 404
    resp = client.get(url, **auth(body["access_token"]))
    assert resp.status_code == 200
    data = resp.json()
    for key in ("job_id", "state", "progress", "total_audio_files", "successful_files", "failed_files",
                "current_stage"):
        assert key in data
    assert client.get(url, HTTP_X_JOB_TOKEN=body["access_token"]).status_code == 200


def test_token_of_one_job_cannot_read_another(client):
    a = api_upload(client).json()
    b = api_upload(client).json()
    assert client.get(f"/api/v1/jobs/{b['job_id']}/", **auth(a["access_token"])).status_code == 404
    result = AudioFile.objects.filter(job_id=b["job_id"]).first()
    assert client.get(f"/api/v1/results/{result.id}/download/", **auth(a["access_token"])).status_code == 404


def test_results_and_secure_download(client):
    body = api_upload(client).json()
    resp = client.get(f"/api/v1/jobs/{body['job_id']}/results/", **auth(body["access_token"]))
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["transcription"]["status"] == "DONE"
    assert result["extraction"]["status"] == "DONE"
    assert isinstance(result["extraction"]["data"], dict)
    url = result["pdf"]["download_url"]
    assert client.get(url).status_code == 404  # anonymous
    dl = client.get(url, **auth(body["access_token"]))
    assert dl.status_code == 200
    assert dl["Content-Type"] == "application/pdf"
    assert b"".join(dl.streaming_content).startswith(b"%PDF")


def test_signed_download_link(client):
    body = api_upload(client).json()
    f = AudioFile.objects.get(job_id=body["job_id"])
    sig = access.sign_download(f.id, 3600)
    assert client.get(f"/api/v1/results/{f.id}/download/?sig={sig}").status_code == 200
    assert client.get(f"/api/v1/results/{f.id}/download/?sig={sig}x").status_code == 404
    other = access.sign_download("00000000-0000-0000-0000-000000000000", 3600)
    assert client.get(f"/api/v1/results/{f.id}/download/?sig={other}").status_code == 404


def test_expired_signed_link(client, monkeypatch):
    body = api_upload(client).json()
    f = AudioFile.objects.get(job_id=body["job_id"])
    sig = access.sign_download(f.id, 3600)
    import time

    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 7200)
    assert client.get(f"/api/v1/results/{f.id}/download/?sig={sig}").status_code == 404


def test_openapi_schema_available(client):
    resp = client.get("/api/schema/")
    assert resp.status_code == 200
    assert b"/api/v1/jobs/" in resp.content


def test_ui_upload_requires_csrf_and_grants_session():
    from django.test import Client

    browser = Client(enforce_csrf_checks=True)
    page = browser.get("/")
    assert page.status_code == 200
    token = page.cookies["csrftoken"].value
    no_csrf = browser.post("/upload/", {"file": upload_file(), "email": "a@example.com"})
    assert no_csrf.status_code == 403
    resp = browser.post("/upload/", {"file": upload_file(), "email": "a@example.com"}, HTTP_X_CSRFTOKEN=token)
    assert resp.status_code == 202, resp.content
    job_id = resp.json()["job_id"]
    assert browser.get(f"/jobs/{job_id}/").status_code == 200
    assert browser.get(f"/api/v1/jobs/{job_id}/").status_code == 200  # session grant
    assert Client().get(f"/jobs/{job_id}/").status_code == 404  # another browser
    assert len(mail.outbox) == 1


def test_signed_job_link_grants_session_and_strips_signature():
    from django.test import Client

    body = api_upload(APIClient()).json()
    sig = access.sign_job_link(body["job_id"], 3600)
    browser = Client()
    resp = browser.get(f"/jobs/{body['job_id']}/?sig={sig}")
    assert resp.status_code == 302 and "sig=" not in resp["Location"]
    assert browser.get(resp["Location"]).status_code == 200
    assert Client().get(f"/jobs/{body['job_id']}/?sig=forged").status_code == 404


def test_security_headers(client):
    resp = client.get("/")
    assert "default-src 'self'" in resp["Content-Security-Policy"]
    assert resp["X-Frame-Options"] == "DENY"
