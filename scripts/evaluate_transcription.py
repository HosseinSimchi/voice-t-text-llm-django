"""Compare transcription quality on representative Persian samples.

Put pairs into a directory:  sample1.wav + sample1.txt (reference transcript, UTF-8).
Run:  python scripts/evaluate_transcription.py tests/samples [--model small] [--model medium]

Prints word error rate (WER) and character error rate (CER) per file and overall,
after the same Persian normalisation the pipeline applies.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
os.environ.setdefault("LOG_TO_FILE", "false")

AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac", ".opus"}
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def _edit_distance(a: list, b: list) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def _clean(text: str) -> str:
    from apps.transcription.text import normalize_persian

    return " ".join(_PUNCT.sub(" ", normalize_persian(text).replace("‌", " ")).split())


def evaluate_directory(directory: Path, stt_cfg: dict) -> dict:
    import tempfile

    from apps.transcription.audio import normalize
    from apps.transcription.engine import get_engine

    engine = get_engine(stt_cfg)
    rows, w_err, w_tot, c_err, c_tot = [], 0, 0, 0, 0
    for audio in sorted(p for p in directory.iterdir() if p.suffix.lower() in AUDIO_EXT):
        ref_path = audio.with_suffix(".txt")
        if not ref_path.is_file():
            continue
        with tempfile.TemporaryDirectory() as tmp:
            wav = normalize(audio, Path(tmp) / "n.wav", stt_cfg.get("preprocessing", {}), 4 * 3600)
            hyp = _clean(engine.transcribe(wav).text)
        ref = _clean(ref_path.read_text(encoding="utf-8"))
        we, ce = _edit_distance(ref.split(), hyp.split()), _edit_distance(list(ref), list(hyp))
        w_err, w_tot, c_err, c_tot = w_err + we, w_tot + len(ref.split()), c_err + ce, c_tot + len(ref)
        rows.append({"file": audio.name, "wer": round(we / max(1, len(ref.split())), 3),
                     "cer": round(ce / max(1, len(ref)), 3)})
    return {"model": stt_cfg["model"], "files": len(rows), "rows": rows,
            "wer": round(w_err / max(1, w_tot), 3), "cer": round(c_err / max(1, c_tot), 3)}


def main() -> None:
    import django

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--model", action="append", help="Whisper model(s) to compare (default: configured)")
    args = parser.parse_args()
    django.setup()
    from apps.core.config import get_config

    base = dict(get_config().stt)
    for model in args.model or [base["model"]]:
        print(json.dumps(evaluate_directory(args.directory, {**base, "model": model}), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
