from django.core.files.uploadedfile import SimpleUploadedFile

from tests.builders import wav_bytes, zip_bytes


def upload_file(name="audio.zip", data=None, content_type="application/zip"):
    if data is None:
        data = zip_bytes({"meeting.wav": wav_bytes(1.0)})
    return SimpleUploadedFile(name, data, content_type=content_type)


def api_upload(client, data=None, name="audio.zip", email="user@example.com", content_type="application/zip"):
    return client.post("/api/v1/jobs/", {"file": upload_file(name, data, content_type), "email": email},
                       format="multipart")


def auth(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}
