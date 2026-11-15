"""Check the e-mail setup in seconds, without running a whole job.

    python manage.py send_test_email you@example.com                 # a short test message
    python manage.py send_test_email you@example.com --job latest    # re-send a finished job's real result e-mail
    python manage.py send_test_email you@example.com --job <job_id>  # (with the ZIP of its PDFs)

The message is sent through the configured SMTP server, so it proves the credentials, the network path and
the ZIP attachment. Job state is not changed.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage, get_connection
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from apps.core.logging import mask_email
from apps.notifications.services import build_message
from apps.processing.models import Job, JobStatus


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("to", help="recipient address")
        parser.add_argument("--job", help="job id, or 'latest', to re-send its real result e-mail (with the ZIP)")

    def handle(self, *args, to, job=None, **options):
        try:
            validate_email(to)
        except ValidationError as exc:
            raise CommandError(f"'{to}' is not a valid e-mail address.") from exc
        if not settings.EMAIL_REAL_DELIVERY:
            raise CommandError(
                f"EMAIL_BACKEND is {settings.EMAIL_BACKEND}: messages are not sent to anyone. Set "
                "EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend and EMAIL_HOST/PORT/USE_TLS/HOST_USER/"
                "HOST_PASSWORD in .env.local (or the environment), then run this again."
            )
        self.stdout.write(
            f"SMTP server: {settings.EMAIL_HOST}:{settings.EMAIL_PORT} (TLS={settings.EMAIL_USE_TLS}, "
            f"SSL={settings.EMAIL_USE_SSL}) | login: {mask_email(settings.EMAIL_HOST_USER) or '(none)'} | "
            f"from: {settings.DEFAULT_FROM_EMAIL}"
        )
        message = self._message(to, job)
        try:
            with get_connection(fail_silently=False) as connection:
                sent = connection.send_messages([message])
        except Exception as exc:  # noqa: BLE001 - report every kind of failure readably
            raise CommandError(f"The SMTP server did not accept the message: {type(exc).__name__}: {exc}") from exc
        if not sent:
            raise CommandError("The SMTP server did not accept the message.")
        attachments = ", ".join(f"{a[0]} ({len(a[1]) // 1024} KB)" for a in message.attachments) or "none"
        self.stdout.write(self.style.SUCCESS(
            f"Accepted by the SMTP server for {mask_email(to)} (attachments: {attachments}). "
            "Now check the inbox, and the spam folder."
        ))

    def _message(self, to: str, job_ref: str | None):
        if not job_ref:
            return EmailMessage(
                subject="Audio Intelligence: SMTP test",
                body="If you can read this, the SMTP settings of Audio Intelligence work.",
                from_email=settings.DEFAULT_FROM_EMAIL, to=[to],
            )
        if job_ref == "latest":
            job = Job.objects.filter(status__in=[JobStatus.COMPLETED, JobStatus.PARTIALLY_COMPLETED],
                                     results_deleted_at__isnull=True).order_by("-created_at").first()
            if job is None:
                raise CommandError("There is no finished job with results to re-send.")
        else:
            job = Job.objects.filter(pk=job_ref).first()
            if job is None:
                raise CommandError(f"No job with id {job_ref}.")
        if job.results_deleted_at:
            raise CommandError("The results of that job have expired.")
        self.stdout.write(f"Re-sending the result e-mail of job {job.id} ({job.status}).")
        message = build_message(job)
        message.to = [to]
        return message
