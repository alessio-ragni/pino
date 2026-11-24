"""The server: a websocket for devices, two routes for permissions, one to know it is alive.

Keep it behind Tailscale or the home network. Every request carries the token
`PINO_TOKEN`: without it, the server refuses.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, WebSocket

from pino import speech
from pino.agent import Agent
from pino.bell import ring_forever
from pino.config import Settings
from pino.session import AgentFactory, Session
from pino.store import Store

log = logging.getLogger("pino")

PURGE_EVERY_S = 6 * 3600


def _try(make, s: Settings, what: str):
    try:
        return make(s)
    except Exception as bad:  # noqa: BLE001 — the server starts anyway, without that part
        log.warning("%s not available: %s", what, bad)
        return None


def create_app(
    s: Settings | None = None,
    *,
    stt: speech.Transcriber | None = None,
    tts: speech.Speaker | None = None,
    agent_factory: AgentFactory = Agent,
    bell: bool = True,
) -> FastAPI:
    s = s or Settings.from_env()
    if not s.token:
        raise RuntimeError("PINO_TOKEN is missing from .env: without a token the server does not start.")
    store = Store(s.db_path, s.audio_dir)
    stt = stt or _try(speech.transcriber, s, "transcription")
    tts = tts or _try(speech.speaker, s, "voice")
    sessions: list[Session] = []

    async def purge_forever() -> None:
        while True:
            removed = store.purge(s.audio_days)
            if removed:
                log.info("removed %d audio files older than %d days", removed, s.audio_days)
            await asyncio.sleep(PURGE_EVERY_S)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        tasks = [asyncio.create_task(purge_forever())]
        if bell:
            tasks.append(asyncio.create_task(ring_forever(store, s.tz, lambda: list(sessions))))
        yield
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="Pino", lifespan=lifespan)

    def allowed(token: str) -> bool:
        return hmac.compare_digest(token.encode(), s.token.encode())

    @app.get("/salute")
    def health() -> dict:
        return {
            "ok": True,
            "model": s.model,
            "stt": stt.name if stt else None,
            "tts": tts.name if tts else None,
            "a2ui": s.a2ui_version,
            "devices": len(sessions),
        }

    @app.get("/permessi")
    def trust_list(token: str = Query("")) -> list[dict]:
        if not allowed(token):
            raise HTTPException(401)
        return store.trust_list()

    @app.post("/permessi/ritira")
    def trust_revoke(tool: str = Query(...), token: str = Query("")) -> dict:
        if not allowed(token):
            raise HTTPException(401)
        store.revoke(tool)
        return {"ok": True}

    @app.websocket("/ws")
    async def device(ws: WebSocket, token: str = "", device: str = "tablet") -> None:
        if not allowed(token):
            await ws.close(code=4401)
            return
        await ws.accept()
        session = Session(ws, s, store, stt, tts, device, agent_factory)
        sessions.append(session)
        try:
            await session.run()
        finally:
            sessions.remove(session)

    app.state.store = store
    app.state.sessions = sessions
    return app
