from celery import shared_task

from . import services


@shared_task(name="notifications.send_job_email", acks_late=True, ignore_result=True)
def send_job_email(job_id: str) -> None:
    services.send_job_email(job_id)
