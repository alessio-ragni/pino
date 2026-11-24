"""All configuration comes from the environment (or `.env`). No hard-coded values."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# The household connectors Pino keeps. Every other MCP server of the host is switched off
# for Pino: each one adds tool descriptions to every request, and slows every answer.
HOME_CONNECTORS = "WhatsApp,Gmail,Google Calendar,Google Drive"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    host: str
    port: int
    token: str
    model: str
    effort: str
    tz: str
    stt: str
    tts: str
    openai_api_key: str
    openai_stt_model: str
    openai_tts_model: str
    openai_voice: str
    elevenlabs_api_key: str
    elevenlabs_voice_id: str
    elevenlabs_stt_model: str
    elevenlabs_tts_model: str
    audio_days: int
    a2ui_version: str
    confirm_timeout_s: float
    connectors: tuple[str, ...] = field(default_factory=lambda: tuple(HOME_CONNECTORS.split(",")))
    lang: str = "it"
    idle_reset_min: float = 10
    filler_s: float = 3.0

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> Settings:
        load_dotenv(env_file or Path.cwd() / ".env")
        return cls(
            data_dir=Path(_get("PINO_DATA", str(Path.home() / ".pino"))).expanduser(),
            host=_get("PINO_HOST", "0.0.0.0"),
            port=int(_get("PINO_PORT", "4390")),
            token=_get("PINO_TOKEN"),
            # For a voice, readiness matters most: Haiku with little effort. Sonnet or Opus by changing a line.
            model=_get("PINO_MODEL", "claude-haiku-5-5"),
            effort=_get("PINO_EFFORT", "low"),
            tz=_get("PINO_TZ", "Europe/Rome"),
            stt=_get("PINO_STT", "openai"),
            tts=_get("PINO_TTS", "openai"),
            openai_api_key=_get("OPENAI_API_KEY"),
            openai_stt_model=_get("PINO_OPENAI_STT_MODEL", "gpt-4o-transcribe"),
            openai_tts_model=_get("PINO_OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
            openai_voice=_get("PINO_OPENAI_VOICE", "ash"),
            elevenlabs_api_key=_get("ELEVENLABS_API_KEY"),
            elevenlabs_voice_id=_get("PINO_ELEVENLABS_VOICE_ID"),
            elevenlabs_stt_model=_get("PINO_ELEVENLABS_STT_MODEL", "scribe_v1"),
            elevenlabs_tts_model=_get("PINO_ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5"),
            audio_days=int(_get("PINO_AUDIO_DAYS", "30")),
            a2ui_version=_get("PINO_A2UI_VERSION", "v0.9.1"),
            confirm_timeout_s=float(_get("PINO_CONFIRM_TIMEOUT_S", "120")),
            connectors=tuple(c.strip() for c in _get("PINO_CONNECTORS", HOME_CONNECTORS).split(",") if c.strip()),
            lang=_get("PINO_LANG", "it"),
            idle_reset_min=float(_get("PINO_IDLE_RESET_MIN", "10")),
            filler_s=float(_get("PINO_FILLER_S", "3")),
        )

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "pino.db"

    @property
    def work_dir(self) -> Path:
        """The folder Claude runs in: empty, its own, away from the host's files."""
        return self.data_dir / "lavoro"
