"""Raw PCM from the tablet: 16-bit, mono, little-endian. Only the minimum to make a WAV."""

from __future__ import annotations

import io
import sys
import wave
from array import array

INPUT_RATE = 16_000

# Speech from afar arrives quiet: before transcribing it is brought to a normal level.
TARGET_PEAK = 16_000
MAX_GAIN = 8.0


def louder(pcm: bytes) -> bytes:
    """Raises the volume of a quiet recording (never beyond MAX_GAIN, never to clipping).

    The reference is the 99.9th percentile sample, not the maximum: a single bang must not
    stop everything else from being raised.
    """
    samples = array("h", pcm[: len(pcm) - len(pcm) % 2])
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return pcm
    loud = sorted(abs(x) for x in samples)[int(len(samples) * 0.999) - 1 if len(samples) > 1 else 0]
    if loud <= 0:
        return pcm
    gain = min(MAX_GAIN, TARGET_PEAK / loud)
    if gain <= 1.05:
        return pcm
    out = array("h", (max(-32768, min(32767, int(x * gain))) for x in samples))
    if sys.byteorder != "little":
        out.byteswap()
    return out.tobytes()


def to_wav(pcm: bytes, rate: int = INPUT_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def seconds(pcm: bytes, rate: int = INPUT_RATE) -> float:
    return len(pcm) / 2 / rate
