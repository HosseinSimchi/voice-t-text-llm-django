"""Helpers that build audio files and ZIP/RAR archives in memory."""

from __future__ import annotations

import io
import math
import struct
import wave
import zipfile
import zlib


def wav_bytes(seconds: float = 1.0, rate: int = 16000, freq: float = 440.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(int(seconds * rate)):
            frames += struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i / rate)))
        w.writeframes(bytes(frames))
    return buf.getvalue()


def zip_bytes(entries: dict[str, bytes], *, symlinks: dict[str, str] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
        for name, target in (symlinks or {}).items():
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = (0o120777 << 16)
            zf.writestr(info, target)
    return buf.getvalue()


def _rar4_block(head_type: int, flags: int, body: bytes) -> bytes:
    size = 7 + len(body)
    without_crc = struct.pack("<BHH", head_type, flags, size) + body
    crc = zlib.crc32(without_crc) & 0xFFFF
    return struct.pack("<H", crc) + without_crc


def rar_bytes(entries: dict[str, bytes]) -> bytes:
    """A RAR 4.x archive with *stored* (uncompressed) entries.

    Stored entries are read by ``rarfile`` directly, so tests need no unrar binary.
    """
    out = bytearray(b"Rar!\x1a\x07\x00")
    out += _rar4_block(0x73, 0x0000, b"\x00" * 6)  # main archive header
    for name, data in entries.items():
        raw_name = name.encode("utf-8")
        body = struct.pack(
            "<IIBIIBBHI",
            len(data), len(data), 3, zlib.crc32(data) & 0xFFFFFFFF,
            0x5A210000,  # DOS date/time
            29, 0x30, len(raw_name), 0o100644,
        ) + raw_name
        out += _rar4_block(0x74, 0x8000, body) + data  # LONG_BLOCK: data follows the header
    out += _rar4_block(0x7B, 0x4000, b"")
    return bytes(out)
