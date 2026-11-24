"""Understanding and speaking. Anthropic offers neither, so this leans on outside services.

Only two things, the same for any service:

* `Transcriber.transcribe(wav) -> text`
* `Speaker.speak(text) -> chunks of 16-bit mono PCM at `sample_rate``

The service is chosen in `.env` (`PINO_STT`, `PINO_TTS`). To add one:
a file in this folder and a line in the two dictionaries.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Protocol

from pino.config import Settings


class Transcriber(Protocol):
    name: str

    async def transcribe(self, wav: bytes) -> str: ...


class Speaker(Protocol):
    name: str
    sample_rate: int

    def speak(self, text: str) -> AsyncIterator[bytes]: ...


def _openai_stt(s: Settings) -> Transcriber:
    from .openai_speech import OpenAITranscriber

    return OpenAITranscriber(s)


def _openai_tts(s: Settings) -> Speaker:
    from .openai_speech import OpenAISpeaker

    return OpenAISpeaker(s)


def _eleven_stt(s: Settings) -> Transcriber:
    from .elevenlabs_speech import ElevenLabsTranscriber

    return ElevenLabsTranscriber(s)


def _eleven_tts(s: Settings) -> Speaker:
    from .elevenlabs_speech import ElevenLabsSpeaker

    return ElevenLabsSpeaker(s)


TRANSCRIBERS: dict[str, Callable[[Settings], Transcriber]] = {
    "openai": _openai_stt,
    "elevenlabs": _eleven_stt,
}
SPEAKERS: dict[str, Callable[[Settings], Speaker]] = {
    "openai": _openai_tts,
    "elevenlabs": _eleven_tts,
}


def transcriber(s: Settings) -> Transcriber:
    if s.stt not in TRANSCRIBERS:
        raise ValueError(f"PINO_STT={s.stt!r}: choose among {', '.join(TRANSCRIBERS)}")
    return TRANSCRIBERS[s.stt](s)


def speaker(s: Settings) -> Speaker:
    if s.tts not in SPEAKERS:
        raise ValueError(f"PINO_TTS={s.tts!r}: choose among {', '.join(SPEAKERS)}")
    return SPEAKERS[s.tts](s)
