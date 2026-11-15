"""Content-based (magic byte) detection of archive and audio formats.

Extensions and client MIME types are never trusted on their own: the actual
bytes must match the claimed extension.
"""

from __future__ import annotations

ZIP_MAGIC = b"PK\x03\x04"
ZIP_EMPTY_MAGIC = b"PK\x05\x06"
RAR4_MAGIC = b"Rar!\x1a\x07\x00"
RAR5_MAGIC = b"Rar!\x1a\x07\x01\x00"

ARCHIVE_MIME_TYPES = {
    "zip": {"application/zip", "application/x-zip-compressed", "application/x-zip", "multipart/x-zip"},
    "rar": {"application/vnd.rar", "application/x-rar-compressed", "application/x-rar"},
}
GENERIC_MIME_TYPES = {"application/octet-stream", "binary/octet-stream", ""}

# Which content families are acceptable for each extension.
AUDIO_EXTENSION_FAMILIES: dict[str, set[str]] = {
    "mp3": {"mp3"},
    "wav": {"wav"},
    "flac": {"flac"},
    "ogg": {"ogg"},
    "opus": {"ogg"},
    "m4a": {"mp4"},
    "aac": {"aac", "mp4"},
}

NESTED_ARCHIVE_EXTENSIONS = {"zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz"}


def sniff_archive(header: bytes) -> str | None:
    if header.startswith(ZIP_MAGIC):
        return "zip"
    if header.startswith(RAR5_MAGIC) or header.startswith(RAR4_MAGIC):
        return "rar"
    return None


def sniff_audio(header: bytes) -> str | None:
    """Return the audio container family of ``header`` (first >= 12 bytes) or None."""
    if len(header) < 4:
        return None
    if header.startswith(b"ID3"):
        return "mp3"
    if header[:4] == b"RIFF" and header[8:12] in (b"WAVE",):
        return "wav"
    if header[:4] == b"RF64" and header[8:12] == b"WAVE":
        return "wav"
    if header.startswith(b"fLaC"):
        return "flac"
    if header.startswith(b"OggS"):
        return "ogg"
    if header[4:8] == b"ftyp":
        return "mp4"
    if header.startswith(b"ADIF"):
        return "aac"
    b0, b1 = header[0], header[1]
    if b0 == 0xFF and (b1 & 0xF6) == 0xF0:  # ADTS: 1111 1111 1111 x00x
        return "aac"
    if b0 == 0xFF and (b1 & 0xE0) == 0xE0 and (b1 & 0x18) != 0x08 and (b1 & 0x06) != 0x00:
        return "mp3"  # MPEG audio frame sync with valid version + layer
    return None


def audio_matches_extension(header: bytes, extension: str) -> bool:
    family = sniff_audio(header)
    return family is not None and family in AUDIO_EXTENSION_FAMILIES.get(extension, set())


def archive_mime_allowed(kind: str, content_type: str | None) -> bool:
    ct = (content_type or "").split(";")[0].strip().lower()
    return ct in GENERIC_MIME_TYPES or ct in ARCHIVE_MIME_TYPES.get(kind, set())
