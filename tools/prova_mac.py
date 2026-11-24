"""Plays the tablet from the Mac, to try the server before the tablet is there.

    cd server && .venv/bin/python ../tools/prova_mac.py                 # voice: Enter to talk, Enter to stop
    cd server && .venv/bin/python ../tools/prova_mac.py --scrivi         # text: type and press Enter (alias --text)

While it waits for a confirmation, answer «sì», «no» or «non chiedermelo più» (spoken or typed).
What would reach the tablet's screen is printed here as A2UI JSON.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import queue
import sys

import websockets

RATE_IN = 16_000


def _player():
    import sounddevice as sd

    q: queue.Queue[bytes | None] = queue.Queue()
    state = {"stream": None, "rate": None}

    def ensure(rate: int):
        if state["rate"] != rate:
            if state["stream"] is not None:
                state["stream"].close()
            state["stream"] = sd.RawOutputStream(samplerate=rate, channels=1, dtype="int16")
            state["stream"].start()
            state["rate"] = rate
        return state["stream"]

    return q, ensure


async def record_until_enter() -> bytes:
    import sounddevice as sd

    chunks: list[bytes] = []

    def cb(indata, frames, t, status):
        chunks.append(bytes(indata))

    loop = asyncio.get_running_loop()
    with sd.RawInputStream(samplerate=RATE_IN, channels=1, dtype="int16", callback=cb):
        await loop.run_in_executor(None, input, "🎙  talk, then Enter… ")
    return b"".join(chunks)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("PINO_URL", "ws://127.0.0.1:4390/ws"))
    ap.add_argument("--token", default=os.environ.get("PINO_TOKEN", ""))
    ap.add_argument("--scrivi", "--text", dest="scrivi", action="store_true", help="type instead of talking")
    args = ap.parse_args()
    if not args.token:
        sys.exit("The token is required: --token or PINO_TOKEN in the environment.")

    _, ensure = _player()
    rate = {"value": 24_000}

    async with websockets.connect(f"{args.url}?token={args.token}&device=mac", max_size=None) as ws:

        async def reader() -> None:
            async for msg in ws:
                if isinstance(msg, bytes):
                    ensure(rate["value"]).write(msg)
                    continue
                data = json.loads(msg)
                kind = data.get("type")
                if kind == "say":
                    rate["value"] = data.get("rate") or rate["value"]
                    print(f"🗣  {data['text']}")
                elif kind == "heard":
                    print(f"👂 {data['text']}")
                elif kind == "a2ui":
                    print("📺 " + json.dumps(data["messages"], ensure_ascii=False, indent=1))
                elif kind == "ready":
                    print(f"✅ connected (voice: {data['voice']}, ears: {data['ears']})")
                elif kind in ("thinking", "done", "say_end"):
                    if kind == "done":
                        print(f"   ({data['ms']} ms)")
                else:
                    print(data)

        task = asyncio.create_task(reader())
        loop = asyncio.get_running_loop()
        try:
            while True:
                if args.scrivi:
                    line = await loop.run_in_executor(None, input, "> ")
                    if line.strip():
                        await ws.send(json.dumps({"type": "text", "text": line}))
                else:
                    await loop.run_in_executor(None, input, "(Enter to talk) ")
                    await ws.send(json.dumps({"type": "start", "rate": RATE_IN}))
                    pcm = await record_until_enter()
                    for i in range(0, len(pcm), 8000):
                        await ws.send(pcm[i : i + 8000])
                    await ws.send(json.dumps({"type": "end", "rate": RATE_IN}))
        except (EOFError, KeyboardInterrupt):
            pass
        finally:
            task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
