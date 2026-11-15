"""Audio probing (real content validation) and normalisation with FFmpeg.

Probing uses PyAV (libav* = FFmpeg libraries, shipped with faster-whisper) so a
file is accepted only if FFmpeg can actually demux an audio stream from it.
Normalisation uses the ``ffmpeg`` CLI (mono, 16 kHz, band-pass + dynamic
normalisation) and falls back to PyAV resampling when the binary is absent.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps.core.exceptions import AudioValidationError, TransientError

logger = logging.getLogger(__name__)


@dataclass
class AudioInfo:
    duration: float
    codec: str
    format_name: str
    sample_rate: int
    channels: int


def probe(path: Path) -> AudioInfo:
    import av

    try:
        with av.open(str(path), mode="r") as container:
            streams = [s for s in container.streams if s.type == "audio"]
            if not streams:
                raise AudioValidationError("The file contains no audio stream.", code="no_audio_stream")
            stream = streams[0]
            duration = None
            if stream.duration is not None and stream.time_base is not None:
                duration = float(stream.duration * stream.time_base)
            if not duration and container.duration:
                duration = container.duration / 1_000_000
            if not duration:
                duration = _decode_duration(container, stream)
            return AudioInfo(
                duration=float(duration or 0.0),
                codec=stream.codec_context.name or "",
                format_name=container.format.name or "",
                sample_rate=int(stream.codec_context.sample_rate or 0),
                channels=int(getattr(stream.codec_context, "channels", 0) or 0),
            )
    except AudioValidationError:
        raise
    except Exception as exc:  # av.error.* and malformed containers
        raise AudioValidationError("The audio file is malformed or cannot be decoded.",
                                   code="malformed_audio") from exc


def _decode_duration(container, stream) -> float:
    last = 0.0
    for frame in container.decode(stream):
        if frame.time is not None:
            last = float(frame.time) + frame.samples / float(frame.sample_rate or 1)
    return last


def validate_audio(path: Path, max_duration: float) -> AudioInfo:
    info = probe(path)
    if info.duration <= 0:
        raise AudioValidationError("The audio file has no decodable duration.", code="empty_audio")
    if info.duration > max_duration:
        raise AudioValidationError(
            f"The audio is longer than the allowed {int(max_duration)} seconds.", code="duration_exceeded"
        )
    return info


def normalize(src: Path, dst: Path, preprocessing: dict[str, Any], max_duration: float) -> Path:
    """Write a mono 16-bit PCM WAV suitable for Whisper. Idempotent (overwrites ``dst``)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp.wav")
    tmp.unlink(missing_ok=True)
    sample_rate = int(preprocessing.get("sample_rate", 16000))
    channels = int(preprocessing.get("channels", 1))
    binary = shutil.which(preprocessing.get("ffmpeg_binary", "ffmpeg"))
    if binary:
        cmd = [binary, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
               "-vn", "-sn", "-dn", "-map", "0:a:0", "-t", str(int(max_duration) + 1),
               "-ac", str(channels), "-ar", str(sample_rate)]
        if preprocessing.get("filters"):
            cmd += ["-af", str(preprocessing["filters"])]
        cmd += ["-c:a", "pcm_s16le", "-f", "wav", str(tmp)]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=max(600, max_duration), check=False)
        except subprocess.TimeoutExpired as exc:
            tmp.unlink(missing_ok=True)
            raise TransientError("Audio normalisation timed out.", code="ffmpeg_timeout") from exc
        if proc.returncode != 0:
            tmp.unlink(missing_ok=True)
            logger.warning("ffmpeg failed for %s: %s", src.name, proc.stderr[-500:].decode("utf-8", "replace"))
            raise AudioValidationError("The audio file could not be decoded by FFmpeg.", code="malformed_audio")
    else:
        _normalize_with_pyav(src, tmp, sample_rate, channels, max_duration)
    tmp.replace(dst)
    return dst


def _normalize_with_pyav(src: Path, dst: Path, sample_rate: int, channels: int, max_duration: float) -> None:
    import av

    layout = "mono" if channels == 1 else "stereo"
    resampler = av.AudioResampler(format="s16", layout=layout, rate=sample_rate)
    max_samples = int((max_duration + 1) * sample_rate)
    written = 0
    try:
        with av.open(str(src)) as container, wave.open(str(dst), "wb") as out:
            out.setnchannels(channels)
            out.setsampwidth(2)
            out.setframerate(sample_rate)
            stream = next(s for s in container.streams if s.type == "audio")
            for frame in container.decode(stream):
                for res in resampler.resample(frame):
                    data = res.to_ndarray().tobytes()
                    out.writeframes(data)
                    written += res.samples
                if written >= max_samples:
                    break
            for res in resampler.resample(None):
                out.writeframes(res.to_ndarray().tobytes())
    except Exception as exc:
        dst.unlink(missing_ok=True)
        raise AudioValidationError("The audio file could not be decoded.", code="malformed_audio") from exc
