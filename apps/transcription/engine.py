"""Speech-to-text engines. Selected by ``stt.engine`` in ``config/ai/stt.yaml``.

``faster_whisper`` is built in; any other value is treated as a dotted path to a
class implementing :class:`TranscriptionEngine` (used for alternative engines and tests).
"""

from __future__ import annotations

import importlib
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from apps.core.exceptions import PermanentError, TransientError

from .text import build_paragraphs, normalize_persian

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    segments: list[dict[str, Any]]
    language: str
    language_probability: float | None
    duration: float | None
    model: str
    paragraphs: list[dict[str, Any]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(p["text"] for p in self.paragraphs)


class TranscriptionEngine(Protocol):
    model_name: str

    def transcribe(self, audio_path: Path) -> TranscriptionResult: ...


class FasterWhisperEngine:
    """Local Faster-Whisper (CTranslate2). Models are cached per process."""

    _models: dict[tuple, Any] = {}
    _lock = threading.Lock()

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.model_name = cfg["model"]

    def _model(self):
        key = (self.cfg["model"], self.cfg["device"], self.cfg["compute_type"], self.cfg.get("download_root"))
        with self._lock:
            if key not in self._models:
                try:
                    from faster_whisper import WhisperModel
                except ImportError as exc:  # pragma: no cover - dependency missing
                    raise PermanentError("faster-whisper is not installed.", code="stt_unavailable") from exc
                logger.info("Loading Whisper model %s on %s (%s)", *key[:3])
                try:
                    self._models[key] = WhisperModel(
                        self.cfg["model"], device=self.cfg["device"], compute_type=self.cfg["compute_type"],
                        cpu_threads=int(self.cfg.get("cpu_threads", 0) or 0),
                        num_workers=int(self.cfg.get("num_workers", 1)),
                        download_root=self.cfg.get("download_root"),
                    )
                except (OSError, RuntimeError) as exc:
                    # Network errors while downloading the model or OOM are worth retrying.
                    raise TransientError(f"Whisper model could not be loaded: {type(exc).__name__}",
                                         code="stt_model_load_failed") from exc
            return self._models[key]

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        model = self._model()
        cfg = self.cfg
        options: dict[str, Any] = {
            "language": cfg.get("language") or None,
            "task": cfg.get("task", "transcribe"),
            "beam_size": int(cfg.get("beam_size", 5)),
            "vad_filter": bool(cfg.get("vad_filter", True)),
            "condition_on_previous_text": bool(cfg.get("condition_on_previous_text", False)),
            "initial_prompt": cfg.get("initial_prompt") or None,
            "word_timestamps": bool(cfg.get("word_timestamps", False)),
        }
        if options["vad_filter"]:
            options["vad_parameters"] = {"min_silence_duration_ms": int(cfg.get("vad_min_silence_ms", 700))}
        if cfg.get("chunk_length"):
            options["chunk_length"] = int(cfg["chunk_length"])
        try:
            segments_iter, info = model.transcribe(load_pcm16_wav(audio_path), **options)
            segments = [
                {"id": i, "start": round(float(s.start), 2), "end": round(float(s.end), 2),
                 "text": normalize_persian(s.text)}
                for i, s in enumerate(segments_iter)  # generator: decoding happens window by window
            ]
        except MemoryError as exc:
            raise TransientError("Out of memory during transcription.", code="stt_out_of_memory") from exc
        return finalize_result(
            segments, info.language, getattr(info, "language_probability", None),
            getattr(info, "duration", None), self.model_name, cfg,
        )


def load_pcm16_wav(path: Path):
    """Read the normalised mono 16 kHz PCM WAV as float32 samples in [-1, 1].

    Passing samples (instead of a path) bypasses faster-whisper's own PyAV decoder,
    which is incompatible with recent PyAV releases; preprocessing already resampled.
    """
    import wave

    import numpy as np

    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2 or w.getframerate() != 16000:
            raise PermanentError("Normalised audio must be 16-bit PCM at 16 kHz.", code="bad_normalized_audio")
        channels = w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return (data.astype(np.float32) / 32768.0)


def finalize_result(segments, language, probability, duration, model, cfg) -> TranscriptionResult:
    ordered = sorted((s for s in segments if s.get("text", "").strip()), key=lambda s: (s["start"], s["end"]))
    para_cfg = cfg.get("paragraphs", {}) or {}
    paragraphs = build_paragraphs(
        ordered, float(para_cfg.get("max_gap_seconds", 2.0)), int(para_cfg.get("max_sentences", 6))
    )
    return TranscriptionResult(ordered, language or "", probability, duration, model, paragraphs)


_BUILTIN = {"faster_whisper": FasterWhisperEngine}


def get_engine(cfg: dict[str, Any]) -> TranscriptionEngine:
    name = cfg["engine"]
    cls = _BUILTIN.get(name)
    if cls is None:
        module, _, attr = name.rpartition(".")
        if not module:
            raise PermanentError(f"Unknown speech-to-text engine '{name}'.", code="stt_unknown_engine")
        cls = getattr(importlib.import_module(module), attr)
    return cls(cfg)
