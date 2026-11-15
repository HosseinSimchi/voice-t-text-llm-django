"""Celery task definitions — thin wrappers around the pipeline services.

Retries are scheduled by the pipeline (database attempt counters + exponential
backoff), so the tasks themselves never rely on Celery's retry state.
"""

from celery import shared_task

from . import maintenance, pipeline


@shared_task(name="processing.run_job", acks_late=True, ignore_result=True)
def run_job(job_id: str) -> None:
    pipeline.run_job(job_id)


@shared_task(name="processing.process_file", acks_late=True, ignore_result=True)
def process_file(file_id: str) -> None:
    pipeline.process_file(file_id)


@shared_task(name="processing.finalize_job", acks_late=True, ignore_result=True)
def finalize_job(job_id: str) -> None:
    pipeline.finalize_job(job_id)


@shared_task(name="processing.recover_jobs", ignore_result=True)
def recover_jobs() -> dict:
    return maintenance.recover_jobs()


@shared_task(name="processing.cleanup_storage", ignore_result=True)
def cleanup_storage() -> dict:
    return maintenance.cleanup_storage()


@shared_task(name="processing.cleanup_job_work", ignore_result=True)
def cleanup_job_work(job_id: str) -> None:
    maintenance.cleanup_job_work(job_id)
