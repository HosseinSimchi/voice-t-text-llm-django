"""Re-run failed stages of a finished job from the data that is still stored.

* default (``--extraction``): re-run only LLM extraction for files whose extraction failed. Transcripts
  are kept, nothing is transcribed again; the PDFs are regenerated with the new result.
* ``--all``: start the whole job again from the retained archive (needs the archive to still exist).

A fresh result e-mail is sent when the job finishes again (the previous one was incomplete).
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.processing import dispatch
from apps.processing.models import EmailStatus, FileStatus, Job, JobStage, JobStatus, StageStatus
from apps.uploads import storage


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("job_id")
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--extraction", action="store_true", help="re-run failed LLM extractions only (default)")
        mode.add_argument("--all", action="store_true", help="re-run everything from the retained archive")

    def handle(self, *args, job_id, all=False, **options):
        job = Job.objects.filter(pk=job_id).first()
        if job is None:
            raise CommandError(f"No job with id {job_id}.")
        if not job.is_terminal:
            raise CommandError(f"Job is still {job.status}; only finished jobs can be reprocessed.")
        with transaction.atomic():
            if all:
                self._reset_all(job)
            else:
                count = self._reset_extraction(job)
                if not count:
                    raise CommandError("No file has a failed extraction; use --all to start over.")
                self.stdout.write(f"Re-running extraction for {count} file(s).")
            job.status, job.outcome = JobStatus.QUEUED, ""
            job.error_code, job.error_message = "", ""
            job.attempts, job.next_attempt_at = 0, None
            job.completed_at = job.results_expire_at = None
            job.email_status, job.email_attempts = EmailStatus.PENDING, 0
            job.email_last_error, job.email_transport = "", ""
            job.work_deleted_at = None
            job.save()
            dispatch.enqueue_job(job.id)
        self.stdout.write(self.style.SUCCESS(f"Job {job.id} queued again."))

    def _reset_extraction(self, job: Job) -> int:
        files = job.files.filter(supported=True, extraction_status=StageStatus.FAILED)
        count = files.count()
        for f in files:
            f.extraction_status, f.extraction_result, f.extraction_meta = StageStatus.PENDING, None, {}
            f.status, f.attempts, f.next_attempt_at = FileStatus.PENDING, 0, None
            f.error_code = f.error_message = ""
            f.save()
        if count:
            job.stage = JobStage.FILE_PROCESSING
        return count

    def _reset_all(self, job: Job) -> None:
        if job.archive_deleted_at or not storage.archive_abspath(job.archive_path).is_file():
            raise CommandError("The archive is no longer stored; the original files must be uploaded again.")
        job.files.all().delete()
        job.stage = JobStage.ARCHIVE_EXTRACTION
