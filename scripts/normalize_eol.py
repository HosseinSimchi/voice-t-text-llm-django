"""Convert the files that Linux containers and shells read to Unix line endings (LF).

    python scripts/normalize_eol.py          # fix in place and report what changed
    python scripts/normalize_eol.py --check  # exit 1 if any file still has CRLF (for CI)

A CRLF shebang (`#!/bin/sh\\r`) makes a container fail with "no such file or directory",
and CR characters in an env file end up inside secrets and passwords.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PATTERNS = ["Dockerfile", "docker-compose*.yml", ".dockerignore", ".env", ".env.example", "requirements*.txt",
            "requirements*.in", "scripts/*.sh", ".gitattributes"]


def main() -> int:
    check = "--check" in sys.argv
    bad = []
    for pattern in PATTERNS:
        for path in sorted(ROOT.glob(pattern)):
            data = path.read_bytes()
            if b"\r" not in data:
                continue
            bad.append(path.relative_to(ROOT).as_posix())
            if not check:
                path.write_bytes(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
    verb = "still has CRLF" if check else "converted to LF"
    for name in bad:
        print(f"{verb}: {name}")
    if not bad:
        print("all Docker-related files already use LF")
    return 1 if (check and bad) else 0


if __name__ == "__main__":
    sys.exit(main())
