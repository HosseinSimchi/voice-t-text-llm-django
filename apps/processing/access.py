"""Registration-free access control for jobs and results.

* Each job gets a 256-bit random access token, returned once at upload time.
  Only its SHA-256 hash is stored.
* Browsers that uploaded through the UI get the job id stored in their session.
* E-mails contain signed, time-limited links (Django signing with SECRET_KEY).

Unauthorised requests receive 404 (not 403) so job/result ids cannot be probed.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from django.core import signing

SESSION_KEY = "authorized_jobs"
MAX_SESSION_JOBS = 50
_SIGN_SALT = "audio-intelligence.download"
_JOB_LINK_SALT = "audio-intelligence.job"


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(job, token: str | None) -> bool:
    if not token:
        return False
    return hmac.compare_digest(job.access_token_hash, hash_token(token))


def extract_token(request) -> str | None:
    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.META.get("HTTP_X_JOB_TOKEN") or None


def grant_session(request, job_id) -> None:
    jobs = [j for j in request.session.get(SESSION_KEY, []) if j != str(job_id)]
    jobs.append(str(job_id))
    request.session[SESSION_KEY] = jobs[-MAX_SESSION_JOBS:]
    request.session.modified = True


def session_allows(request, job_id) -> bool:
    session = getattr(request, "session", None)
    return session is not None and str(job_id) in session.get(SESSION_KEY, [])


def can_access_job(request, job) -> bool:
    return session_allows(request, job.id) or token_matches(job, extract_token(request))


def sign_download(result_id, max_age_seconds: int) -> str:
    return signing.dumps({"r": str(result_id), "ttl": int(max_age_seconds)}, salt=_SIGN_SALT, compress=True)


def verify_download_signature(sig: str, result_id) -> bool:
    try:
        payload = signing.loads(sig, salt=_SIGN_SALT, max_age=None)
        signing.loads(sig, salt=_SIGN_SALT, max_age=int(payload.get("ttl", 0)))
    except (signing.BadSignature, signing.SignatureExpired, TypeError, ValueError):
        return False
    return payload.get("r") == str(result_id)


def sign_job_link(job_id, max_age_seconds: int) -> str:
    return signing.dumps({"j": str(job_id), "ttl": int(max_age_seconds)}, salt=_JOB_LINK_SALT, compress=True)


def verify_job_link(sig: str, job_id) -> bool:
    try:
        payload = signing.loads(sig, salt=_JOB_LINK_SALT, max_age=None)
        signing.loads(sig, salt=_JOB_LINK_SALT, max_age=int(payload.get("ttl", 0)))
    except (signing.BadSignature, signing.SignatureExpired, TypeError, ValueError):
        return False
    return payload.get("j") == str(job_id)


_ZIP_SALT = "audio-intelligence.zip"


def sign_zip(job_id, max_age_seconds: int) -> str:
    return signing.dumps({"j": str(job_id), "ttl": int(max_age_seconds)}, salt=_ZIP_SALT, compress=True)


def verify_zip_signature(sig: str, job_id) -> bool:
    try:
        payload = signing.loads(sig, salt=_ZIP_SALT, max_age=None)
        signing.loads(sig, salt=_ZIP_SALT, max_age=int(payload.get("ttl", 0)))
    except (signing.BadSignature, signing.SignatureExpired, TypeError, ValueError):
        return False
    return payload.get("j") == str(job_id)
