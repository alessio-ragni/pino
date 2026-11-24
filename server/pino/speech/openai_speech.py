"""OpenAI: gpt-4o-transcribe to understand, gpt-4o-mini-tts to speak (PCM at 24 kHz)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from pino.config import Settings

VOICE_STYLE = (
    "Speak in the language of the text (usually Italian), warm and natural, like a friend at home. "
    "Easy pace, no announcer emphasis."
)


def _client(s: Settings):
    if not s.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is missing from the server .env.")
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=s.openai_api_key)


class OpenAITranscriber:
    name = "openai"

    def __init__(self, s: Settings) -> None:
        self.model = s.openai_stt_model
        self.client = _client(s)

    async def transcribe(self, wav: bytes) -> str:
        out = await self.client.audio.transcriptions.create(
            model=self.model,
            file=("voce.wav", wav, "audio/wav"),
            # Language detected on its own (Italian or English). No hint with the names: on silence the
            # transcriber repeats it word for word, and it would look like a call.
        )
        return (out.text or "").strip()


class OpenAISpeaker:
    name = "openai"
    sample_rate = 24_000

    def __init__(self, s: Settings) -> None:
        self.model = s.openai_tts_model
        self.voice = s.openai_voice
        self.client = _client(s)

    async def speak(self, text: str) -> AsyncIterator[bytes]:
        async with self.client.audio.speech.with_streaming_response.create(
            model=self.model,
            voice=self.voice,
            input=text,
            instructions=VOICE_STYLE,
            response_format="pcm",
        ) as response:
            async for chunk in response.iter_bytes(4800):
                yield chunk
