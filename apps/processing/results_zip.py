"""One ZIP with the PDFs of every successfully processed audio file of a job."""

from __future__ import annotations

import io
import re
import zipfile

from apps.uploads import storage

from .models import AudioFile, FileStatus, Job

_UNSAFE = re.compile(r"[\x00-\x1f\x7f\\/:*?\"<>|]+")


def zip_name(job: Job) -> str:
    return f"results-{job.id.hex[:8]}.zip"


def pdf_files(job: Job) -> list[AudioFile]:
    """Files that have a PDF on disk (complete or only the transcript PDF), in archive order."""
    return [
        f for f in job.files.all()
        if f.supported and f.has_pdf
        and f.status in (FileStatus.COMPLETED, FileStatus.PARTIALLY_COMPLETED)
        and storage.results_abspath(f.pdf_path).is_file()
    ]


def entry_name(f: AudioFile) -> str:
    """``001-<original name without extension>.pdf``: the index keeps names unique and ordered."""
    stem = _UNSAFE.sub("_", f.original_name.rsplit(".", 1)[0])
    stem = re.sub(r"\.{2,}", "_", stem).strip(" .") or "audio"  # no ".." inside an entry name either
    return f"{f.index + 1:03d}-{stem[:120]}.pdf"


def build(files: list[AudioFile]) -> bytes:
    """ZIP bytes for ``files`` (PDFs are already compressed, so entries are only lightly deflated)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=3) as zf:
        for f in files:
            zf.write(storage.results_abspath(f.pdf_path), entry_name(f))
    return buffer.getvalue()
