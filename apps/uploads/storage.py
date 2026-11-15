"""Persistent, isolated, server-named storage for archives, work files and results.

Layout (all below MEDIA_ROOT, a persistent Docker volume)::

    archives/<job_id>/archive.<zip|rar>
    work/<job_id>/extracted/<index>.<ext>
    work/<job_id>/normalized/<index>.wav
    results/<job_id>/<result_id>.pdf
"""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from pathlib import Path
from typing import Iterable

from apps.core.config import get_config
from apps.core.exceptions import ArchiveValidationError

DIR_MODE = 0o750
FILE_MODE = 0o640


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
    return path


def _job_dir(kind: str, job_id: uuid.UUID | str) -> Path:
    job_uuid = uuid.UUID(str(job_id))  # refuses anything that is not a UUID
    return get_config().storage_dir(kind) / str(job_uuid)


def archive_dir(job_id) -> Path:
    return _job_dir("archive", job_id)


def work_dir(job_id) -> Path:
    return _job_dir("work", job_id)


def results_dir(job_id) -> Path:
    return _job_dir("results", job_id)


def safe_join(base: Path, relative: str) -> Path:
    """Resolve ``relative`` under ``base`` and refuse anything escaping it."""
    resolved = (base / relative).resolve()
    if base.resolve() not in resolved.parents:
        raise PermissionError("Path escapes its storage directory.")
    return resolved


def persist_archive(chunks: Iterable[bytes], job_id, kind: str, max_bytes: int) -> tuple[str, int, str]:
    """Durably write the uploaded archive. Returns (relative path, size, sha256)."""
    target_dir = _ensure_dir(archive_dir(job_id))
    target = target_dir / f"archive.{kind}"
    tmp = target_dir / f".upload-{uuid.uuid4().hex}.part"
    digest = hashlib.sha256()
    size = 0
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), FILE_MODE)
    try:
        with os.fdopen(fd, "wb") as out:
            for chunk in chunks:
                size += len(chunk)
                if size > max_bytes:
                    raise ArchiveValidationError("The archive exceeds the maximum upload size.",
                                                 code="archive_too_large")
                digest.update(chunk)
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    rel = str(target.relative_to(get_config().storage_dir("archive"))).replace("\\", "/")
    return rel, size, digest.hexdigest()


def archive_abspath(rel: str) -> Path:
    return safe_join(get_config().storage_dir("archive"), rel)


def work_abspath(rel: str) -> Path:
    return safe_join(get_config().storage_dir("work"), rel)


def results_abspath(rel: str) -> Path:
    return safe_join(get_config().storage_dir("results"), rel)


def relative_to_kind(kind: str, path: Path) -> str:
    return str(path.resolve().relative_to(get_config().storage_dir(kind).resolve())).replace("\\", "/")


def remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=False)


def atomic_write_bytes(target: Path, data: bytes) -> None:
    _ensure_dir(target.parent)
    tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), FILE_MODE)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def ensure_dir(path: Path) -> Path:
    return _ensure_dir(path)
