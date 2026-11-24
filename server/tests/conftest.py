from __future__ import annotations

from pathlib import Path

import pytest

from pino.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        host="127.0.0.1",
        port=0,
        token="prova",
        model="finto",
        effort="low",
        tz="Europe/Rome",
        stt="openai",
        tts="openai",
        openai_api_key="",
        openai_stt_model="",
        openai_tts_model="",
        openai_voice="",
        elevenlabs_api_key="",
        elevenlabs_voice_id="",
        elevenlabs_stt_model="",
        elevenlabs_tts_model="",
        audio_days=30,
        a2ui_version="v0.9.1",
        confirm_timeout_s=2,
    )
