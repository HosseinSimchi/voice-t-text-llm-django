"""Safe inspection and extraction of ZIP and RAR archives.

Security model
--------------
* Archive member names are NEVER used as filesystem paths. Extracted audio is
  written to ``<job work dir>/<index>.<ext>`` with a server-generated name.
* Entries with absolute paths, drive letters or ``..`` components make the whole
  archive invalid (Zip Slip / path traversal attempt).
* Symlinks, devices, encrypted entries and nested archives are reported as
  unsupported and never extracted.
* Size limits are enforced twice: on the declared sizes during upload
  validation and on the actual number of bytes while streaming (headers can lie),
  which stops decompression bombs.
* RAR data is streamed through ``rarfile``, which pipes the external tool's
  stdout (``unrar p`` / ``7z x -so`` ...) — the tool never writes to disk itself.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import stat
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Iterator

import rarfile

from apps.core.exceptions import ArchiveValidationError

from .sniffing import NESTED_ARCHIVE_EXTENSIONS, audio_matches_extension, sniff_archive

logger = logging.getLogger(__name__)

CHUNK = 1024 * 1024
_DRIVE = re.compile(r"^[A-Za-z]:")
_CONTROL = re.compile(r"[\x00-\x1f\x7f‎‏‪-‮⁦-⁩]")


@dataclass
class Limits:
    max_archive_bytes: int
    max_extracted_bytes: int
    max_file_bytes: int
    max_files: int
    max_entries: int
    max_compression_ratio: float
    allowed_audio_extensions: set[str]

    @classmethod
    def from_config(cls, uploads: dict[str, Any]) -> "Limits":
        return cls(
            max_archive_bytes=int(uploads["max_archive_bytes"]),
            max_extracted_bytes=int(uploads["max_extracted_bytes"]),
            max_file_bytes=int(uploads["max_file_bytes"]),
            max_files=int(uploads["max_files"]),
            max_entries=int(uploads["max_entries"]),
            max_compression_ratio=float(uploads["max_compression_ratio"]),
            allowed_audio_extensions={e.lower() for e in uploads["allowed_audio_extensions"]},
        )


@dataclass
class ArchiveEntry:
    index: int
    display_name: str
    extension: str
    size: int
    compressed_size: int
    reject_reason: str = ""
    ref: Any = field(default=None, repr=False)

    @property
    def accepted(self) -> bool:
        return not self.reject_reason


@dataclass
class ExtractedFile:
    index: int
    display_name: str
    extension: str
    path: Path | None
    size: int
    reject_reason: str = ""


# --------------------------------------------------------------------------
# Names
# --------------------------------------------------------------------------
def is_unsafe_member_name(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if "\x00" in normalized or normalized.startswith("/") or _DRIVE.match(normalized):
        return True
    return any(part == ".." for part in PurePosixPath(normalized).parts)


def display_name_for(name: str) -> str:
    """Sanitised basename for display only (never used as a path)."""
    base = PurePosixPath(name.replace("\\", "/")).name
    base = unicodedata.normalize("NFC", _CONTROL.sub("", base)).strip()
    return (base or "audio")[:200]


def extension_of(name: str) -> str:
    suffix = PurePosixPath(name.replace("\\", "/")).suffix
    return suffix[1:].lower() if suffix else ""


def _zip_member_name(info: zipfile.ZipInfo) -> str:
    """Recover UTF-8 names stored without the UTF-8 flag (common for Persian names)."""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


# --------------------------------------------------------------------------
# RAR tool selection
# --------------------------------------------------------------------------
_RAR_TOOLS = {"unrar": "unrar", "unar": "unar", "bsdtar": "bsdtar", "7z": "7z", "7zz": "7zz"}


def detect_rar_tool(preference: str = "auto") -> str | None:
    candidates = list(_RAR_TOOLS) if preference == "auto" else [preference]
    for name in candidates:
        if shutil.which(_RAR_TOOLS.get(name, name)):
            return name
    return None


def configure_rarfile(preference: str = "auto") -> str | None:
    tool = detect_rar_tool(preference)
    if tool is None:
        return None
    try:
        rarfile.tool_setup(
            unrar=tool == "unrar", unar=tool == "unar", bsdtar=tool == "bsdtar",
            sevenzip=tool == "7z", sevenzip2=tool == "7zz", force=True,
        )
    except rarfile.RarCannotExec:
        return None
    return tool


# --------------------------------------------------------------------------
# Inspection
# --------------------------------------------------------------------------
def detect_archive_kind(path: Path) -> str:
    with open(path, "rb") as fh:
        header = fh.read(16)
    kind = sniff_archive(header)
    if kind is None:
        raise ArchiveValidationError("The file is not a valid ZIP or RAR archive.", code="invalid_archive_format")
    return kind


def _classify(index: int, raw_name: str, size: int, csize: int, *, is_dir: bool, is_link: bool,
              encrypted: bool, limits: Limits, ref: Any) -> ArchiveEntry | None:
    if is_dir:
        return None
    if is_unsafe_member_name(raw_name):
        raise ArchiveValidationError(
            "The archive contains an unsafe path (absolute path or '..'); it was rejected.",
            code="archive_path_traversal",
        )
    ext = extension_of(raw_name)
    entry = ArchiveEntry(index=index, display_name=display_name_for(raw_name), extension=ext,
                         size=size, compressed_size=csize, ref=ref)
    if is_link:
        entry.reject_reason = "symbolic_link_not_allowed"
    elif encrypted:
        entry.reject_reason = "encrypted_entry_not_supported"
    elif ext in NESTED_ARCHIVE_EXTENSIONS:
        entry.reject_reason = "nested_archive_not_supported"
    elif ext not in limits.allowed_audio_extensions:
        entry.reject_reason = "unsupported_file_type"
    elif size > limits.max_file_bytes:
        entry.reject_reason = "file_too_large"
    elif size == 0:
        entry.reject_reason = "empty_file"
    return entry


def _check_ratio(entry: ArchiveEntry, limits: Limits) -> None:
    if entry.size > CHUNK and entry.compressed_size > 0:
        if entry.size / entry.compressed_size > limits.max_compression_ratio:
            raise ArchiveValidationError(
                "The archive has a suspicious compression ratio (possible decompression bomb).",
                code="archive_compression_ratio",
            )


def _zip_entries(path: Path, limits: Limits) -> tuple[zipfile.ZipFile, list[ArchiveEntry]]:
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError) as exc:
        raise ArchiveValidationError("The ZIP archive is corrupted or unreadable.", code="corrupt_archive") from exc
    infos = zf.infolist()
    if len(infos) > limits.max_entries:
        zf.close()
        raise ArchiveValidationError("The archive contains too many entries.", code="too_many_entries")
    entries: list[ArchiveEntry] = []
    with _Closing(zf):
        for i, info in enumerate(infos):
            mode = (info.external_attr >> 16) & 0xFFFF
            is_link = stat.S_ISLNK(mode) if info.create_system == 3 else False
            special = info.create_system == 3 and mode and not (
                stat.S_ISREG(mode) or stat.S_ISDIR(mode) or is_link)
            entry = _classify(
                i, _zip_member_name(info), info.file_size, info.compress_size,
                is_dir=info.is_dir(), is_link=is_link or bool(special), encrypted=bool(info.flag_bits & 0x1),
                limits=limits, ref=info,
            )
            if entry:
                _check_ratio(entry, limits)
                entries.append(entry)
    return zf, entries


def _rar_entries(path: Path, limits: Limits, tool_preference: str) -> tuple[rarfile.RarFile, list[ArchiveEntry]]:
    configure_rarfile(tool_preference)
    try:
        rf = rarfile.RarFile(str(path))
    except (rarfile.Error, OSError) as exc:
        raise ArchiveValidationError("The RAR archive is corrupted or unreadable.", code="corrupt_archive") from exc
    if rf.needs_password():
        rf.close()
        raise ArchiveValidationError("Password-protected archives are not supported.", code="encrypted_archive")
    infos = rf.infolist()
    if len(infos) > limits.max_entries:
        rf.close()
        raise ArchiveValidationError("The archive contains too many entries.", code="too_many_entries")
    entries: list[ArchiveEntry] = []
    with _Closing(rf):
        for i, info in enumerate(infos):
            entry = _classify(
                i, info.filename, int(info.file_size or 0), int(info.compress_size or 0),
                is_dir=info.is_dir(), is_link=info.is_symlink() or not (info.is_file() or info.is_dir()),
                encrypted=info.needs_password(), limits=limits, ref=info,
            )
            if entry:
                _check_ratio(entry, limits)
                entries.append(entry)
    return rf, entries


def _open_archive(path: Path, kind: str, limits: Limits, tool_preference: str):
    if kind == "zip":
        return _zip_entries(path, limits)
    if kind == "rar":
        return _rar_entries(path, limits, tool_preference)
    raise ArchiveValidationError("Unsupported archive type.", code="invalid_archive_format")


class _Closing:
    """Close the archive if classification raises (so a rejected file can be deleted on Windows)."""

    def __init__(self, archive):
        self.archive = archive

    def __enter__(self):
        return self.archive

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.archive.close()
        return False


def inspect_archive(path: Path, kind: str, limits: Limits, tool_preference: str = "auto") -> list[ArchiveEntry]:
    """Validate structure and declared sizes. Raises ArchiveValidationError for unusable archives."""
    archive, entries = _open_archive(path, kind, limits, tool_preference)
    archive.close()
    accepted = [e for e in entries if e.accepted]
    if not entries:
        raise ArchiveValidationError("The archive is empty.", code="empty_archive")
    if len(accepted) > limits.max_files:
        raise ArchiveValidationError(
            f"The archive contains more than {limits.max_files} audio files.", code="too_many_files"
        )
    if sum(e.size for e in accepted) > limits.max_extracted_bytes:
        raise ArchiveValidationError(
            "The total extracted size of the audio files exceeds the allowed limit.", code="extracted_too_large"
        )
    if not accepted:
        raise ArchiveValidationError(
            "The archive does not contain any supported audio file (mp3, wav, m4a, aac, ogg, flac, opus).",
            code="no_supported_audio",
        )
    return entries


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------
def _member_stream(archive: Any, entry: ArchiveEntry) -> BinaryIO:
    return archive.open(entry.ref)


def _copy_limited(src: BinaryIO, dest: Path, limit: int, budget: int) -> int:
    """Stream ``src`` into ``dest`` (created exclusively) refusing more than ``min(limit, budget)`` bytes."""
    cap = min(limit, budget)
    written = 0
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o640)
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = src.read(CHUNK)
                if not chunk:
                    break
                written += len(chunk)
                if written > cap:
                    raise _LimitExceeded("file_too_large" if cap == limit else "extraction_size_limit_reached")
                out.write(chunk)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return written


class _LimitExceeded(Exception):
    pass


def iter_extract(path: Path, kind: str, dest_dir: Path, limits: Limits,
                 tool_preference: str = "auto") -> Iterator[ExtractedFile]:
    """Extract accepted audio entries into ``dest_dir`` yielding one result per entry.

    Failures of individual entries are reported (``reject_reason``) and never stop
    the remaining entries. Raises ArchiveValidationError only for archive-level problems.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive, entries = _open_archive(path, kind, limits, tool_preference)
    budget = limits.max_extracted_bytes
    accepted_count = 0
    try:
        for entry in entries:
            if not entry.accepted:
                yield ExtractedFile(entry.index, entry.display_name, entry.extension, None, entry.size,
                                    entry.reject_reason)
                continue
            accepted_count += 1
            if accepted_count > limits.max_files:
                yield ExtractedFile(entry.index, entry.display_name, entry.extension, None, entry.size,
                                    "too_many_files")
                continue
            target = dest_dir / f"{entry.index:04d}.{entry.extension}"
            target.unlink(missing_ok=True)
            reason = ""
            size = 0
            try:
                with _member_stream(archive, entry) as src:
                    size = _copy_limited(src, target, limits.max_file_bytes, budget)
                budget -= size
                with open(target, "rb") as fh:
                    header = fh.read(64)
                if not audio_matches_extension(header, entry.extension):
                    reason = "content_does_not_match_extension"
            except _LimitExceeded as exc:
                reason = str(exc)
            except rarfile.RarCannotExec:
                logger.error("No RAR extraction tool available for compressed entry in %s", path.name)
                reason = "rar_tool_unavailable"
            except (zipfile.BadZipFile, rarfile.Error, EOFError, OSError, RuntimeError, ValueError) as exc:
                logger.warning("Entry %s of %s could not be extracted: %s", entry.index, path.name, type(exc).__name__)
                reason = "corrupt_entry"
            if reason:
                target.unlink(missing_ok=True)
                yield ExtractedFile(entry.index, entry.display_name, entry.extension, None, size, reason)
            else:
                yield ExtractedFile(entry.index, entry.display_name, entry.extension, target, size)
    finally:
        archive.close()
