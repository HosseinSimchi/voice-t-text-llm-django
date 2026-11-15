"""Result e-mail construction and idempotent, retrying delivery.

Delivery state lives on the Job (email_status / email_attempts). A message is
sent at most once per successful SMTP acceptance: the job is claimed under a
lease, ``SENT`` is recorded immediately after the SMTP server accepts the
message, and every later invocation sees ``SENT`` and does nothing.

Note: SMTP acceptance means the configured server took responsibility for the
message. It does not prove delivery into the recipient's inbox.
"""

from __future__ import annotations

import logging
import smtplib
import socket
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.core.config import get_config
from apps.core.logging import mask_email
from apps.information_extraction.services.display import flatten
from apps.processing import access, dispatch, leases, results_zip
from apps.processing.messages import error_text
from apps.processing.models import EmailStatus, FileStatus, Job, JobStage, JobStatus
from apps.processing.pipeline import complete_job
from apps.uploads import storage

logger = logging.getLogger(__name__)

TRANSIENT_SMTP = (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, socket.timeout,
                  TimeoutError, ConnectionError, OSError)


def is_transient_smtp_error(exc: Exception) -> bool:
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = [c for c, _ in exc.recipients.values()]
        return bool(codes) and all(400 <= c < 500 for c in codes)
    if isinstance(exc, smtplib.SMTPResponseException):
        return 400 <= exc.smtp_code < 500
    if isinstance(exc, smtplib.SMTPException):
        return isinstance(exc, (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError))
    return isinstance(exc, TRANSIENT_SMTP)


def build_message(job: Job) -> EmailMultiAlternatives:
    cfg = get_config()
    email_cfg = cfg.email
    files = list(job.files.all())
    supported = [f for f in files if f.supported]
    successes = [f for f in supported if f.status in (FileStatus.COMPLETED, FileStatus.PARTIALLY_COMPLETED)
                 and f.has_pdf]
    failed = [f for f in files if f not in successes]
    ttl = int(email_cfg.get("download_link_ttl_seconds", 604800))

    # One ZIP with every PDF is the default attachment ("zip"); "pdf" attaches each PDF separately.
    attach_format = email_cfg.get("attach_format", "zip")
    limit = int(email_cfg.get("max_attachment_total_bytes", 15 * 1024 * 1024))
    zip_payload: bytes | None = None
    attach = bool(email_cfg.get("attach_pdfs", True)) and bool(successes)
    if attach:
        if attach_format == "zip":
            zip_payload = results_zip.build(results_zip.pdf_files(job))
            attach = len(zip_payload) <= limit
        else:
            attach = sum(f.pdf_size for f in successes) <= limit
    base = settings.SITE_BASE_URL
    zip_link = ""
    if successes and not attach:  # too large for e-mail: signed, time-limited download links instead
        zip_link = f"{base}{reverse('api-job-download', args=[job.id])}?sig={access.sign_zip(job.id, ttl)}"
    rows = []
    pdf_cfg = cfg.pdf.get("extraction", {})
    for f in files:
        link = ""
        if f in successes and not attach:
            sig = access.sign_download(f.id, ttl)
            link = f"{base}{reverse('api-result-download', args=[f.id])}?sig={sig}"
        rows.append({
            "file": f,
            "ok": f in successes,
            "error": error_text(f.error_code, "fa", f.error_message) if f not in successes else "",
            "link": link,
            "extraction": flatten(f.extraction_result, cfg.extraction_schema, pdf_cfg.get("fields", "*"),
                                  pdf_cfg.get("labels")) if email_cfg.get("include_extracted_information", True)
            else [],
        })
    status_link = f"{base}{reverse('web-job', args=[job.id])}?sig={access.sign_job_link(job.id, ttl)}"
    context = {
        "job": job,
        "outcome": job.outcome,
        "rows": rows,
        "total": len(files),
        "supported": len(supported),
        "success_count": len(successes),
        "failed_count": len(failed),
        "attached": attach and bool(successes),
        "zip_attached": attach and attach_format == "zip" and bool(successes),
        "zip_name": results_zip.zip_name(job),
        "zip_link": zip_link,
        "status_link": status_link,
        "link_days": max(1, ttl // 86400),
        "job_error": error_text(job.error_code, "fa", job.error_message),
    }
    subject_status = {
        JobStatus.COMPLETED: "تکمیل شد",
        JobStatus.PARTIALLY_COMPLETED: "به‌صورت ناقص انجام شد",
        JobStatus.FAILED: "ناموفق بود",
    }.get(job.outcome, job.outcome)
    message = EmailMultiAlternatives(
        subject=f"نتیجه پردازش فایل‌های صوتی — {subject_status}",
        body=render_to_string("notifications/result_email.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[job.email],
        headers={"Message-ID": f"<job-{job.id}@audio-intelligence.local>", "X-Job-ID": str(job.id)},
    )
    message.attach_alternative(render_to_string("notifications/result_email.html", context), "text/html")
    if attach and zip_payload is not None:
        message.attach(results_zip.zip_name(job), zip_payload, "application/zip")
    elif attach:
        for f in successes:
            message.attach(results_zip.entry_name(f), storage.results_abspath(f.pdf_path).read_bytes(),
                           "application/pdf")
    return message


def send_job_email(job_id) -> None:
    actions = []
    with leases.leased(Job, job_id) as owner:
        if not owner:
            return
        job = Job.objects.get(pk=job_id)
        if job.stage != JobStage.EMAIL_DELIVERY or job.email_status in (
            EmailStatus.SENT, EmailStatus.NOT_REQUIRED, EmailStatus.FAILED,
        ):
            return  # idempotency: never send twice
        job.email_status = EmailStatus.SENDING
        job.email_attempts += 1
        job.save(update_fields=["email_status", "email_attempts", "updated_at"])
        try:
            message = build_message(job)
            with get_connection(fail_silently=False) as connection:
                sent = connection.send_messages([message])
            if not sent:
                raise smtplib.SMTPServerDisconnected("The SMTP backend did not accept the message.")
        except Exception as exc:  # noqa: BLE001 - classified below
            actions = _handle_failure(job, exc)
        else:
            job.email_status = EmailStatus.SENT
            job.email_sent_at = timezone.now()
            job.email_message_id = message.extra_headers.get("Message-ID", "")[:255]
            job.email_transport = "smtp" if settings.EMAIL_REAL_DELIVERY else settings.EMAIL_BACKEND.rsplit(".", 2)[-2]
            job.email_last_error = ""
            job.save()
            if settings.EMAIL_REAL_DELIVERY:
                logger.info("Result e-mail for job %s accepted by SMTP for %s", job.id, mask_email(job.email))
            else:
                logger.warning("Result e-mail for job %s was NOT delivered: backend %s does not use SMTP",
                               job.id, settings.EMAIL_BACKEND)
            complete_job(job)
    for action in actions:
        action()


def _handle_failure(job: Job, exc: Exception) -> list:
    cfg = get_config()
    transient = is_transient_smtp_error(exc)
    logger.warning("E-mail for job %s failed (%s, transient=%s)", job.id, type(exc).__name__, transient)
    job.email_last_error = f"{type(exc).__name__}"[:500]
    if transient and job.email_attempts < int(cfg.retry_for("email")["max_attempts"]):
        delay = cfg.backoff_delay(job.email_attempts, "email")
        job.email_status = EmailStatus.RETRYING
        job.status = JobStatus.RETRYING
        job.retry_count += 1
        job.next_attempt_at = timezone.now() + timedelta(seconds=delay)
        job.save()
        return [lambda: dispatch.enqueue_email(job.id, countdown=delay)]
    job.email_status = EmailStatus.FAILED
    job.error_code = "email_delivery_failed"
    job.error_message = "The result e-mail could not be delivered to the SMTP server."
    job.save()
    complete_job(job, status=JobStatus.FAILED)
    return []
