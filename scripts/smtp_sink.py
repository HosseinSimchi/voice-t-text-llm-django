"""A tiny local SMTP server for testing real SMTP delivery. It accepts every message and stores it as .eml.

    python scripts/smtp_sink.py --port 2525 --out media/smtp-sink

Point the app at it (no TLS, no login):
    EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend EMAIL_HOST=127.0.0.1 EMAIL_PORT=2525
    EMAIL_USE_TLS=false

``--fail-first N`` answers the first N messages with a temporary 451 error (to exercise SMTP retries).
"""

import argparse
import asyncio
import pathlib
import time


async def handle(reader, writer, out: pathlib.Path, state: dict):
    def send(line: str):
        writer.write((line + "\r\n").encode())

    send("220 smtp-sink ready")
    sender, rcpts = "", []
    try:
        while True:
            raw = await reader.readline()
            if not raw:
                break
            cmd = raw.decode("utf-8", "replace").strip()
            up = cmd.upper()
            if up.startswith(("EHLO", "HELO")):
                send("250-smtp-sink")
                send("250 8BITMIME")
            elif up.startswith("MAIL FROM"):
                sender, rcpts = cmd[10:].strip(), []
                send("250 ok")
            elif up.startswith("RCPT TO"):
                rcpts.append(cmd[8:].strip())
                send("250 ok")
            elif up == "DATA":
                send("354 end with <CRLF>.<CRLF>")
                await writer.drain()
                lines = []
                while True:
                    line = await reader.readline()
                    if line in (b".\r\n", b""):
                        break
                    lines.append(line[1:] if line.startswith(b"..") else line)
                if state["fail_first"] > 0:
                    state["fail_first"] -= 1
                    send("451 4.3.0 temporary failure, try again later")
                    print("rejected (temporary failure)", flush=True)
                else:
                    state["count"] += 1
                    name = out / f"{int(time.time())}-{state['count']}.eml"
                    name.write_bytes(b"".join(lines))
                    print(f"accepted from {sender} to {rcpts} -> {name.name} ({sum(map(len, lines))} bytes)", flush=True)
                    send("250 2.0.0 queued")
            elif up in ("RSET", "NOOP"):
                send("250 ok")
            elif up == "QUIT":
                send("221 bye")
                await writer.drain()
                break
            else:
                send("502 command not implemented")
            await writer.drain()
    finally:
        writer.close()


async def main(port: int, out: pathlib.Path, fail_first: int):
    out.mkdir(parents=True, exist_ok=True)
    state = {"count": 0, "fail_first": fail_first}
    server = await asyncio.start_server(lambda r, w: handle(r, w, out, state), "127.0.0.1", port)
    print(f"SMTP sink listening on 127.0.0.1:{port}, writing to {out}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=2525)
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("media/smtp-sink"))
    ap.add_argument("--fail-first", type=int, default=0)
    args = ap.parse_args()
    asyncio.run(main(args.port, args.out, args.fail_first))
