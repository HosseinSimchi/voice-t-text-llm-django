"""The result e-mail carries ONE ZIP with the PDF of every successfully processed file."""

import io
import zipfile

import pytest
from django.core import mail
from django.test import Client
from rest_framework.test import APIClient

from apps.processing import access, results_zip
from apps.processing.models import AudioFile, Job
from tests.builders import wav_bytes, zip_bytes
from tests.helpers import api_upload, auth

pytestmark = pytest.mark.django_db(transaction=True)


def _upload(entries=None, client=None):
    body = api_upload(client or APIClient(), zip_bytes(entries or {"a.wav": wav_bytes(1.0), "b.wav": wav_bytes(1.0)})).json()
    return Job.objects.get(pk=body["job_id"]), body["access_token"]


def _zip_of(content: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(content))


def test_email_has_one_zip_attachment_with_every_pdf():
    job, _ = _upload({"جلسه اول.wav": wav_bytes(1.0), "دوم.wav": wav_bytes(1.0), "سوم.wav": wav_bytes(1.0)})
    (name, content, mimetype), = mail.outbox[0].attachments
    assert mimetype == "application/zip" and name == results_zip.zip_name(job)
    with _zip_of(content) as zf:
        assert zf.testzip() is None
        assert zf.namelist() == ["001-جلسه اول.pdf", "002-دوم.pdf", "003-سوم.pdf"]
        assert all(zf.read(n).startswith(b"%PDF") for n in zf.namelist())
    assert "ZIP" in mail.outbox[0].body and name in mail.outbox[0].body


def test_pdfs_in_the_zip_are_byte_identical_to_the_stored_results():
    from apps.uploads import storage

    job, _ = _upload()
    with _zip_of(mail.outbox[0].attachments[0][1]) as zf:
        for f, name in zip(job.files.all(), zf.namelist()):
            assert zf.read(name) == storage.results_abspath(f.pdf_path).read_bytes()


def test_attach_format_pdf_keeps_separate_attachments(app_config):
    app_config.edit_yaml("app.yaml", lambda d: d["notifications"]["email"].update(attach_format="pdf"))
    _upload()
    assert [a[2] for a in mail.outbox[0].attachments] == ["application/pdf", "application/pdf"]


def test_invalid_attach_format_is_rejected_at_startup(app_config):
    from apps.core.config import ConfigError

    with pytest.raises(ConfigError, match="attach_format"):
        app_config.edit_yaml("app.yaml", lambda d: d["notifications"]["email"].update(attach_format="rar"))


def test_failed_files_are_left_out_and_partial_results_still_zipped():
    _upload({"good.wav": wav_bytes(1.0), "broken.wav": b"RIFF\x00\x00\x00\x00WAVEjunkjunkjunk"})
    with _zip_of(mail.outbox[0].attachments[0][1]) as zf:
        assert zf.namelist() == ["001-good.pdf"]


def test_too_large_zip_is_replaced_by_a_signed_link_that_downloads_it(app_config):
    app_config.edit_yaml("app.yaml", lambda d: d["notifications"]["email"].update(max_attachment_total_bytes=10))
    job, _ = _upload()
    msg = mail.outbox[0]
    assert msg.attachments == []
    marker = f"/api/v1/jobs/{job.id}/download/?sig="
    assert marker in msg.body and marker in msg.alternatives[0][0]
    url = "/api/v1/jobs/" + str(job.id) + "/download/?sig=" + msg.body.split(marker)[1].split()[0]
    client = APIClient()
    resp = client.get(url)
    assert resp.status_code == 200 and resp["Content-Type"] == "application/zip"
    with _zip_of(b"".join(resp.streaming_content)) as zf:
        assert len(zf.namelist()) == 2
    assert client.get(url + "x").status_code == 404  # tampered signature


def test_zip_endpoint_requires_the_job_token_or_session():
    job, token = _upload()
    other_job, other_token = _upload()
    url = f"/api/v1/jobs/{job.id}/download/"
    client = APIClient()
    assert client.get(url).status_code == 404  # anonymous: no oracle
    assert client.get(url, **auth("wrong")).status_code == 404
    assert client.get(url, **auth(other_token)).status_code == 404  # another job's token
    ok = client.get(url, **auth(token))
    assert ok.status_code == 200 and ok["Content-Type"] == "application/zip"
    assert ok["Content-Disposition"].startswith("attachment") and results_zip.zip_name(job) in ok["Content-Disposition"]
    with _zip_of(b"".join(ok.streaming_content)) as zf:
        assert len(zf.namelist()) == 2


def test_a_signature_for_one_job_does_not_open_another_jobs_zip():
    job, _ = _upload()
    other, _ = _upload()
    sig = access.sign_zip(job.id, 3600)
    client = APIClient()
    assert client.get(f"/api/v1/jobs/{job.id}/download/?sig={sig}").status_code == 200
    assert client.get(f"/api/v1/jobs/{other.id}/download/?sig={sig}").status_code == 404
    # a per-file download signature must not work as a zip signature either
    file_sig = access.sign_download(job.files.first().id, 3600)
    assert client.get(f"/api/v1/jobs/{job.id}/download/?sig={file_sig}").status_code == 404


def test_zip_is_gone_after_result_retention_and_unavailable_without_pdfs():
    job, token = _upload()
    url = f"/api/v1/jobs/{job.id}/download/"
    AudioFile.objects.filter(job=job).update(pdf_status="FAILED")
    assert APIClient().get(url, **auth(token)).status_code == 404
    AudioFile.objects.filter(job=job).update(pdf_status="DONE")
    Job.objects.filter(pk=job.pk).update(results_deleted_at=job.uploaded_at)
    assert APIClient().get(url, **auth(token)).status_code == 410


def test_results_endpoint_and_status_page_offer_the_zip():
    browser = Client()
    body = api_upload(APIClient(), zip_bytes({"a.wav": wav_bytes(1.0)})).json()
    job_id, token = body["job_id"], body["access_token"]
    results = APIClient().get(f"/api/v1/jobs/{job_id}/results/", **auth(token)).json()
    assert results["download_all_url"] == f"/api/v1/jobs/{job_id}/download/"
    sig = access.sign_job_link(job_id, 3600)
    page = browser.get(browser.get(f"/jobs/{job_id}/?sig={sig}")["Location"])
    assert page.status_code == 200 and f"/api/v1/jobs/{job_id}/download/" in page.content.decode()
    assert browser.get(f"/api/v1/jobs/{job_id}/download/").status_code == 200  # session grant works


def test_entry_names_are_unique_safe_and_ordered():
    class F:
        def __init__(self, index, name):
            self.index, self.original_name = index, name

    cases = [(0, "../../evil.wav", "001-____evil.pdf"), (1, "a/b\\c:d?.mp3", "002-a_b_c_d_.pdf"),
             (2, "\x00\x1f.wav", "003-_.pdf"), (3, "جلسه ۱.mp3", "004-جلسه ۱.pdf"), (4, "  .wav", "005-audio.pdf"),
             (5, "...wav", "006-_.pdf"), (6, "same.wav", "007-same.pdf"), (7, "same.wav", "008-same.pdf")]
    names = [results_zip.entry_name(F(i, n)) for i, n, _ in cases]
    assert names == [expected for _, _, expected in cases]
    assert all("/" not in n and "\\" not in n and ".." not in n for n in names) and len(set(names)) == len(names)
