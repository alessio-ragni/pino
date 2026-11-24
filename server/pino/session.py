"""One connected device: from the websocket to the voice and the screen, and back.

The protocol is in `docs/protocol.md`. In short: the tablet sends `start`, then
binary PCM chunks (16 kHz, 16-bit, mono), then `end`. The server answers with
`heard` (what it understood), a series of `say` each followed by its binary
audio and closed by `say_end`, the cards (`card` and `a2ui` messages), and
`done` at the end of the turn.

Every turn is written in the journal (`turns`, `tool_calls`, `events`) with its
timings, so "why was it slow" and "what did it do" have an answer afterwards.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
import re
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import WebSocket

from pino import a2ui, home
from pino.addressed import called, echo, silent, stopped
from pino.agent import Agent
from pino.audio import INPUT_RATE, louder, to_wav
from pino.config import Settings
from pino.confirm import ACTIONS, Gate, card, read_answer
from pino.speech import Speaker, Transcriber
from pino.store import Store
from pino.text import Splitter

log = logging.getLogger("pino.session")

MIN_SECONDS = 0.3
CHAT = "chat"
AGENDA = "agenda"
MEMORY = "memory"

# Why the tablet started listening. Without a reason, the most careful case holds.
WHY_NAME, WHY_FOLLOW, WHY_BARGE = "name", "follow", "barge"
FOLLOW_PREFIX = "[follow-up, no name] "

TAG = re.compile(r"\[card:\s*([A-Za-z0-9_-]+)\s*\]")

PHRASES = {
    "it": {
        "broken": "Non arrivo al mio cervello. Riprova tra poco.",
        "not_heard": "Non ti ho sentito bene, me lo ripeti?",
        "yes_or_no": "Dimmi sì, no, oppure non chiedermelo più.",
        "confirm": "Lo faccio?",
        "fillers": ["Un attimo.", "Vediamo.", "Dammi un secondo."],
        "timer": "Il timer è finito",
        "reminder": "Ti ricordo",
        "late": "in ritardo di {n} minuti",
        "chat": "Conversazione",
        "agenda": "Sveglie e promemoria",
        "list": "Lista",
        "shopping": "Lista della spesa",
        "when": "Quando",
        "what": "Cosa",
        "where": "Dove suona",
        "clock": "Orologio del tablet",
        "memory": "Cosa so di te",
        "about": "Su",
        "fact": "Ricordo",
        "kinds": {"alarm": "Sveglia", "timer": "Timer", "reminder": "Promemoria"},
        "days": ["lun", "mar", "mer", "gio", "ven", "sab", "dom"],
    },
    "en": {
        "broken": "I can't reach my brain. Try again in a moment.",
        "not_heard": "I didn't catch that, can you say it again?",
        "yes_or_no": "Say yes, no, or don't ask me again.",
        "confirm": "Shall I?",
        "fillers": ["One moment.", "Let me see.", "Just a second."],
        "timer": "The timer is done",
        "reminder": "A reminder",
        "late": "{n} minutes late",
        "chat": "Conversation",
        "agenda": "Alarms and reminders",
        "list": "List",
        "shopping": "Shopping list",
        "when": "When",
        "what": "What",
        "where": "Rings on",
        "clock": "Tablet clock",
        "memory": "What I know about you",
        "about": "About",
        "fact": "Memory",
        "kinds": {"alarm": "Alarm", "timer": "Timer", "reminder": "Reminder"},
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    },
}

AgentFactory = Callable[..., Any]


def _content(sentence: str) -> set[str]:
    return {w for w in re.findall(r"\w+", sentence.lower()) if len(w) > 3}


def repeats(sentence: str, earlier: list[str], threshold: float = 0.6) -> bool:
    """True if `sentence` mostly says again something already said in this turn.

    A small model sometimes says the same thing before and after drawing a card: the second
    one is dropped rather than heard twice.
    """
    plain = " ".join(re.findall(r"\w+", sentence.lower()))
    if len(plain) >= 8 and any(plain in " ".join(re.findall(r"\w+", e.lower())) for e in earlier):
        return True
    words = _content(sentence)
    if len(words) < 3:
        return False
    return any(len(words & _content(e)) / len(words) >= threshold for e in earlier)


def _drawable(snapshot: list[dict]) -> bool:
    try:
        for m in snapshot:
            if "updateComponents" in m:
                a2ui.validate(m["updateComponents"]["components"])
        return True
    except (a2ui.Invalid, KeyError, TypeError):
        return False


class Lead:
    """Holds the start of an answer until it knows two things: which card it belongs to
    (the `[card:id]` tag, never spoken) and, in a follow-up, whether Claude chose to stay silent."""

    def __init__(self, follow: bool) -> None:
        self.follow = follow
        self.buf = ""
        self.card: str | None = None
        self.done = False

    def feed(self, delta: str) -> str | None:
        if self.done:
            return delta
        self.buf += delta
        rest = self.buf.lstrip()
        if not rest:
            return None
        if rest.startswith("["):
            if "]" not in rest:
                if len(rest) < 48:
                    return None
            else:
                m = TAG.match(rest)
                if m:
                    self.card = m.group(1).lower()
                    rest = rest[m.end() :].lstrip()
                    if not rest:
                        return None
        if self.follow and not rest.strip(" .…"):
            # Only dots so far: maybe Claude is staying silent. Wait for more.
            return None
        self.done = True
        return rest

    @property
    def silent(self) -> bool:
        rest = TAG.sub("", self.buf).strip()
        return not rest or silent(rest)


class Session:
    def __init__(
        self,
        ws: WebSocket,
        s: Settings,
        store: Store,
        stt: Transcriber | None,
        tts: Speaker | None,
        device: str,
        agent_factory: AgentFactory = Agent,
    ) -> None:
        self.ws = ws
        self.s = s
        self.store = store
        self.stt = stt
        self.tts = tts
        self.device = device
        self.words = PHRASES.get(s.lang, PHRASES["it"])
        self.gate = Gate(store, self._ask_confirm, s.confirm_timeout_s, close=self._close_confirm)
        servers = {
            "screen": a2ui.server(self, s.lang),
            "home": home.server(store, self, s.tz),
        }
        self.agent = agent_factory(s, servers, self.gate, self)
        self._lock = asyncio.Lock()
        # What to say, in order: sentences, and markers that say "the turn's voice ends here".
        self._lines: deque[str | asyncio.Event] = deque()
        self._has_lines = asyncio.Event()
        self._cut = False
        self._pcm = bytearray()
        self._recording = False
        self._why = WHY_NAME
        self._said = ""
        self._turn: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()
        # Cards: what is open, what is drawn on this tablet, the one in front.
        self.cards: dict[str, dict] = {c["id"]: c for c in store.cards_open(device)}
        self._drawn: set[str] = set()
        self.front: str | None = None
        self._notes: list[str] = []
        # What Pino knows goes to Claude once per conversation, and again after it changes.
        self._memory_told: float | None = None
        # The turn being answered, for the journal.
        self._turn_id: int | None = None
        self._marks: dict[str, float] = {}
        self._touched: list[str] = []
        self._tools: dict[str, tuple[float, str, Any, str | None]] = {}
        self._last_turn_at = time.monotonic()
        self._device_waits: dict[int, asyncio.Future[bool]] = {}
        self._device_n = 0

    # ── the loop ───────────────────────────────────────────────────────────

    @property
    def busy(self) -> bool:
        return self._recording or (self._turn is not None and not self._turn.done()) or bool(self._lines)

    async def run(self) -> None:
        await self.agent.start()
        speaker = asyncio.create_task(self._speaker_loop())
        idle = asyncio.create_task(self._idle_loop())
        self.store.event("connect", None, self.device)
        try:
            await self._send(
                {
                    "type": "ready",
                    "voice": bool(self.tts),
                    "ears": bool(self.stt),
                    "rate": self.tts.sample_rate if self.tts else None,
                    "a2ui": self.s.a2ui_version,
                }
            )
            await self._replay_cards()
            while True:
                msg = await self.ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    if self._recording:
                        self._pcm.extend(msg["bytes"])
                elif msg.get("text"):
                    try:
                        data = json.loads(msg["text"])
                    except json.JSONDecodeError:
                        continue
                    await self._on_json(data)
        finally:
            self.store.event("disconnect", None, self.device)
            for task in [speaker, idle, self._turn, *self._tasks]:
                if task is not None:
                    task.cancel()
            with contextlib.suppress(Exception):
                await self.agent.stop()

    async def _idle_loop(self) -> None:
        """After a quiet spell the brain starts afresh: a short conversation answers faster."""
        while True:
            await asyncio.sleep(30)
            quiet = time.monotonic() - self._last_turn_at
            if self.busy or quiet < self.s.idle_reset_min * 60 or self.agent.started_at > self._last_turn_at:
                continue
            try:
                await self.agent.restart()
                self.store.event("agent", f"restarted after {int(quiet)} s idle", self.device)
            except Exception as bad:  # noqa: BLE001
                log.exception("restart failed")
                self.store.event("agent", f"restart failed: {bad!r}", self.device)

    async def _on_json(self, m: dict[str, Any]) -> None:
        kind = m.get("type")
        if kind == "start":
            self._why = str(m.get("why") or WHY_NAME)
            # Talking again: Pino goes quiet. Not when the tablet only *thinks* it heard its name
            # over his voice: it turns him down and the server decides once it reads the sentence.
            if self._why != WHY_BARGE:
                self._hush()
            self._pcm.clear()
            self._recording = True
            self._marks = {"start": time.monotonic()}
        elif kind == "end":
            self._recording = False
            pcm = bytes(self._pcm)
            self._pcm.clear()
            self._spawn(self._heard(pcm, int(m.get("rate") or INPUT_RATE), self._why))
        elif kind == "text":
            await self._handle(str(m.get("text", "")).strip(), None, "text")
        elif kind == "action":
            await self._on_action(m)
        elif kind == "stop":
            self._hush()
            if self.gate.pending:
                self.gate.answer("no")
            with contextlib.suppress(Exception):
                await self.agent.interrupt()
        elif kind == "closed":
            cid = str(m.get("surfaceId") or m.get("id") or "")
            if cid in self.cards:
                self.cards.pop(cid)
                self._drawn.discard(cid)
                self.store.card_close(self.device, cid)
                if self.front == cid:
                    self.front = None
        elif kind == "front":
            self.front = str(m.get("surfaceId") or m.get("id") or "") or None
        elif kind == "render_error":
            sid, text = m.get("surfaceId"), str(m.get("message", ""))[:300]
            self.store.event("render_error", {"surfaceId": sid, "message": text}, self.device)
            self._notes.append(f"card {sid} failed to draw: {text}")
        elif kind == "device_result":
            wait = self._device_waits.pop(int(m.get("id") or 0), None)
            if wait is not None and not wait.done():
                wait.set_result(bool(m.get("ok")))
        elif kind == "ring_stop":
            self.store.event("ring_stop", {"id": m.get("id")}, self.device)

    async def _on_action(self, m: dict[str, Any]) -> None:
        name = str(m.get("name", ""))
        if name in ACTIONS:
            if self.gate.answer(ACTIONS[name]):
                await self._close_confirm()
            return
        # Another tap on the screen: told to Claude as a sentence.
        context = json.dumps(m.get("context", {}), ensure_ascii=False)
        await self._handle(f"[on screen, card {m.get('surfaceId')}: tapped «{name}» {context}]", None, "action")

    async def _heard(self, pcm: bytes, rate: int, why: str = WHY_NAME) -> None:
        if len(pcm) / 2 / rate < MIN_SECONDS:
            await self._send({"type": "ignored", "reason": "breve"})
            return
        rid = self.store.save_recording(pcm, self.device, rate)
        if self.stt is None:
            self.store.set_transcript(rid, None, "-", "no transcription service configured")
            await self._send({"type": "error", "text": "Trascrizione non configurata sul server."})
            return
        t0 = time.monotonic()
        try:
            text = await self.stt.transcribe(to_wav(louder(pcm), rate))
        except Exception as bad:  # noqa: BLE001 — written down and said
            log.exception("transcription failed")
            self.store.set_transcript(rid, None, self.stt.name, repr(bad))
            self.say(self.words["not_heard"])
            return
        ms_transcribe = int((time.monotonic() - t0) * 1000)
        # The tablet woke up on its own: if the sentence does not start with the name, nobody called.
        # Right after an answer, only that it is not the echo of his own voice matters.
        if why in (WHY_NAME, WHY_BARGE) and not called(text):
            await self._ignore(rid, "eco" if why == WHY_BARGE else "non chiamato")
            return
        if why in (WHY_FOLLOW, WHY_BARGE) and (not text or echo(text, self._said)):
            await self._ignore(rid, "eco")
            return
        self.store.set_transcript(rid, text, self.stt.name)
        if stopped(text):
            # «Basta», «stop», «grazie»: the conversation is over, back to waiting for the name.
            self._hush()
            with contextlib.suppress(Exception):
                await self.agent.interrupt()
            self.store.event("stop", None, self.device)
            await self._send({"type": "ignored", "reason": "stop"})
            return
        await self._send({"type": "heard", "text": text, "recording": rid})
        if text:
            await self._handle(text, rid, why, ms_transcribe)

    async def _ignore(self, rid: int | None, reason: str) -> None:
        """It was not for Pino: no answer, and neither the audio nor the text is kept."""
        if rid is not None:
            self.store.forget_recording(rid, reason)
        log.info("discarded: %s", reason)
        self.store.event("ignored", reason, self.device)
        await self._send({"type": "ignored", "reason": reason})

    async def _handle(self, text: str, rid: int | None, why: str = "text", ms_transcribe: int | None = None) -> None:
        if not text:
            return
        if self.gate.pending:
            answer = read_answer(text)
            if answer and self.gate.answer(answer):
                await self._close_confirm()
            else:
                self.say(self.words["yes_or_no"])
            return
        if self._turn is not None and not self._turn.done():
            # Talking over an answer: stop it and listen to the new one.
            self._hush()
            with contextlib.suppress(Exception):
                await self.agent.interrupt()
            with contextlib.suppress(BaseException):
                await asyncio.wait_for(self._turn, timeout=5)
        self._turn = asyncio.create_task(self._converse(text, rid, why, ms_transcribe))

    def _context(self) -> str:
        now = datetime.now(ZoneInfo(self.s.tz))
        day = self.words["days"][now.weekday()]
        parts = [f"{day} {now:%d/%m/%Y %H:%M}"]
        parts.append(f"front card: {self.front or 'none'}")
        if self.cards:
            parts.append("open cards: " + ", ".join(f'{c["id"]} "{c["title"]}"' for c in self.cards.values()))
        else:
            parts.append("open cards: none")
        started = getattr(self.agent, "started_at", 0.0)
        if self._memory_told != started:
            self._memory_told = started
            known = "; ".join(
                f"#{m['id']} {m['about'] + ': ' if m['about'] else ''}{m['fact']}" for m in self.store.memories()
            )
            parts.append("what you know: " + (known or "nothing yet"))
        if self._notes:
            parts.append("note: " + "; ".join(self._notes))
            self._notes.clear()
        return "[" + " | ".join(parts) + "] "

    async def _converse(self, text: str, rid: int | None, why: str, ms_transcribe: int | None) -> None:
        follow = why == WHY_FOLLOW
        started = time.monotonic()
        self._last_turn_at = started
        self._turn_id = self.store.start_turn(self.device, why, text, rid, self.s.model)
        self._marks = {"text": started}
        self._touched = []
        await self._send({"type": "thinking"})
        splitter = Splitter(eager_first=True)
        lead = Lead(follow)
        error, outcome = None, "ok"
        answered = ""
        self._said = ""
        filler = asyncio.create_task(self._filler_after(self.s.filler_s))
        said_now: list[str] = []

        def piece(delta: str) -> None:
            if "first_text" not in self._marks:
                self._marks["first_text"] = time.monotonic()
            out = lead.feed(delta)
            if out is None:
                return
            for sentence in splitter.feed(out):
                spoken(sentence)

        def spoken(sentence: str) -> None:
            if repeats(sentence, said_now):
                return
            said_now.append(sentence)
            self.say(sentence)

        try:
            prompt = self._context() + (FOLLOW_PREFIX if follow else "") + text
            answered = await self.agent.ask(prompt, on_text=piece)
            if follow and lead.silent and not self._touched:
                filler.cancel()
                outcome = "silent"
                await self._ignore(rid, "non per me")
                self._journal(answered, None, outcome, None, ms_transcribe)
                return
            if not lead.done:
                rest = lead.feed("")
                if rest:
                    for sentence in splitter.feed(rest):
                        spoken(sentence)
            for sentence in splitter.flush():
                spoken(sentence)
        except asyncio.CancelledError:
            filler.cancel()
            self._journal(answered, lead.card, "interrupted", None, ms_transcribe)
            raise
        except Exception as bad:  # noqa: BLE001
            log.exception("the brain did not answer")
            error, outcome = repr(bad), "error"
            self.say(self.words["broken"])
        filler.cancel()
        # What was really said (repeats dropped) is what the card's thread and the journal keep.
        clean = " ".join(said_now) or TAG.sub("", answered).strip()
        answered = clean
        cid = self._card_for(lead.card, follow)
        if cid and clean and outcome == "ok":
            await self._thread(cid, text, clean)
        # «done» comes after the last sentence said, not before: the tablet knows it can listen again.
        said = asyncio.Event()
        self._lines.append(said)
        self._has_lines.set()
        await said.wait()
        self._journal(answered, cid, outcome, error, ms_transcribe)
        await self._send({"type": "done", "ms": int((time.monotonic() - started) * 1000)})
        self._last_turn_at = time.monotonic()

    def _card_for(self, tagged: str | None, follow: bool) -> str:
        """The card an answer belongs to: the one Claude named, else the one it drew on, else chat."""
        if tagged and (tagged in self.cards or tagged in self._touched):
            return tagged
        if self._touched:
            return self._touched[-1]
        if not tagged and follow and self.front and self.front in self.cards:
            return self.front
        return CHAT

    def _journal(self, answered: str, cid: str | None, outcome: str, error: str | None, ms_transcribe: int | None):
        if self._turn_id is None:
            return
        m, t0 = self._marks, self._marks.get("text", time.monotonic())
        result = getattr(self.agent, "last_result", None)
        usage = (getattr(result, "usage", None) or {}) if result else {}

        def since(key: str) -> int | None:
            return int((m[key] - t0) * 1000) if key in m else None

        self.store.finish_turn(
            self._turn_id,
            answered=TAG.sub("", answered or "").strip(),
            card=cid,
            ms_transcribe=ms_transcribe,
            ms_first_text=since("first_text"),
            ms_first_audio=since("first_audio"),
            ms_total=int((time.monotonic() - t0) * 1000),
            api_ms=getattr(result, "duration_api_ms", None),
            num_turns=getattr(result, "num_turns", None),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            cache_read_tokens=usage.get("cache_read_input_tokens"),
            cost_usd=getattr(result, "total_cost_usd", None),
            outcome=outcome,
            error=error,
        )

    async def _filler_after(self, seconds: float) -> None:
        """Nothing said yet after a few seconds: a short «un attimo», so the silence is not a doubt."""
        if seconds <= 0:
            return
        await asyncio.sleep(seconds)
        if "first_say" not in self._marks:
            self.say(random.choice(self.words["fillers"]))

    # ── tool journal (called by the agent's hooks) ─────────────────────────

    def tool_started(self, tool_use_id: str, tool: str, tool_input: Any, allowed: bool, confirmed: str | None):
        if not allowed:
            self.store.log_tool(self._turn_id, tool, tool_input, 0, False, "denied", confirmed)
            return
        self._tools[tool_use_id] = (time.monotonic(), tool, tool_input, confirmed)

    def tool_finished(self, tool_use_id: str, ok: bool, error: str | None = None):
        started = self._tools.pop(tool_use_id, None)
        if started is None:
            return
        t0, tool, tool_input, confirmed = started
        self.store.log_tool(self._turn_id, tool, tool_input, int((time.monotonic() - t0) * 1000), ok, error, confirmed)

    # ── the voice ──────────────────────────────────────────────────────────

    def say(self, text: str) -> None:
        text = TAG.sub("", text).strip()
        if not text:
            return
        self._marks.setdefault("first_say", time.monotonic())
        # What it said in the turn, to recognize the echo on the next round.
        self._said = (self._said + " " + text)[-2000:]
        self._lines.append(text)
        self._has_lines.set()

    def _hush(self) -> None:
        self._cut = True
        while self._lines:
            item = self._lines.popleft()
            if isinstance(item, asyncio.Event):
                item.set()

    def _fetch(self, text: str) -> asyncio.Queue:
        """Starts the voice for a sentence right away; the chunks wait in a queue."""
        out: asyncio.Queue[bytes | None] = asyncio.Queue()

        async def run() -> None:
            try:
                if self.tts is not None:
                    async for chunk in self.tts.speak(text):
                        await out.put(chunk)
            except Exception:  # noqa: BLE001
                log.exception("the voice got stuck")
            finally:
                await out.put(None)

        self._spawn(run())
        return out

    def _next_line(self) -> str | asyncio.Event | None:
        return self._lines.popleft() if self._lines else None

    async def _speaker_loop(self) -> None:
        """Says the sentences in order. The next sentence's voice is fetched while this one plays."""
        ahead: tuple[str, asyncio.Queue] | None = None
        while True:
            if ahead is None:
                while not self._lines:
                    self._has_lines.clear()
                    await self._has_lines.wait()
                item = self._next_line()
                if isinstance(item, asyncio.Event):
                    item.set()
                    continue
                assert isinstance(item, str)
                current = (item, self._fetch(item))
            else:
                current, ahead = ahead, None
            self._cut = False
            text, chunks = current
            await self._send({"type": "say", "text": text, "rate": self.tts.sample_rate if self.tts else None})
            while True:
                if ahead is None and self._lines and isinstance(self._lines[0], str):
                    nxt = self._lines.popleft()
                    assert isinstance(nxt, str)
                    ahead = (nxt, self._fetch(nxt))
                chunk = await chunks.get()
                if chunk is None or self._cut:
                    break
                if "first_audio" not in self._marks:
                    self._marks["first_audio"] = time.monotonic()
                await self._send_bytes(chunk)
            await self._send({"type": "say_end"})
            if self._cut:
                ahead = None

    # ── cards ──────────────────────────────────────────────────────────────

    def _meta(self, cid: str) -> dict:
        c = self.cards.get(cid, {})
        return {"type": "card", "id": cid, "title": c.get("title", cid), "thread": c.get("thread", [])}

    async def show_card(self, cid: str, title: str, components: list[dict]) -> None:
        """Draws (or redraws in place) a card, remembers it, and brings it in front."""
        create = {"createSurface": {"surfaceId": cid}}
        update = {"updateComponents": {"surfaceId": cid, "components": components}}
        snapshot = a2ui.check([create, update], self.s.a2ui_version)
        send = snapshot if cid not in self._drawn else snapshot[1:]
        self.store.card_put(self.device, cid, title, snapshot)
        prev = self.cards.get(cid, {})
        self.cards[cid] = {"id": cid, "title": title, "thread": prev.get("thread", []), "snapshot": snapshot}
        self._drawn.add(cid)
        if cid not in self._touched:
            self._touched.append(cid)
        await self._send(self._meta(cid))
        await self._send({"type": "a2ui", "messages": send})
        await self._send({"type": "focus", "id": cid})
        self.front = cid

    async def close_card(self, cid: str) -> bool:
        if cid not in self.cards:
            return False
        self.cards.pop(cid)
        self.store.card_close(self.device, cid)
        if cid in self._drawn:
            self._drawn.discard(cid)
            await self._send(
                {"type": "a2ui", "messages": a2ui.check([{"deleteSurface": {"surfaceId": cid}}], self.s.a2ui_version)}
            )
        await self._send({"type": "card_closed", "id": cid})
        if self.front == cid:
            self.front = None
        return True

    async def _thread(self, cid: str, q: str, a: str) -> None:
        if cid not in self.cards:
            title = self.words["chat"] if cid == CHAT else cid
            self.store.card_put(self.device, cid, title, None)
            self.cards[cid] = {"id": cid, "title": title, "thread": [], "snapshot": None}
        self.cards[cid]["thread"] = self.store.card_thread(self.device, cid, q, a)
        await self._send(self._meta(cid))
        await self._send({"type": "focus", "id": cid})
        self.front = cid

    async def _replay_cards(self) -> None:
        """A fresh connection: the tablet forgets its cards and gets them back from here."""
        await self._send({"type": "cards_reset"})
        for cid, c in list(self.cards.items()):
            if c.get("snapshot") and not _drawable(c["snapshot"]):
                # Saved by an older version and no longer passes the checks: better gone than a crash.
                self.cards.pop(cid)
                self.store.card_close(self.device, cid)
                continue
            await self._send(self._meta(cid))
            if c.get("snapshot"):
                await self._send({"type": "a2ui", "messages": c["snapshot"]})
                self._drawn.add(cid)

    # ── household (called by the home tools and the bell) ───────────────────

    async def device_action(self, action: dict[str, Any]) -> bool:
        """Asks the tablet to do something on the device (an alarm on its Clock app) and waits for the answer."""
        self._device_n += 1
        n = self._device_n
        wait = asyncio.get_running_loop().create_future()
        self._device_waits[n] = wait
        await self._send({"type": "device", "id": n, **action})
        try:
            return await asyncio.wait_for(wait, timeout=6)
        except TimeoutError:
            return False
        finally:
            self._device_waits.pop(n, None)

    async def agenda_changed(self, show: bool = True) -> None:
        if not show and AGENDA not in self.cards:
            return
        now = home.local_now(self.s.tz)
        w = self.words
        rows = []
        for r in home.agenda_rows(self.store, now):
            where = w["clock"] if r.get("on_device") else "Pino"
            rows.append(
                [r["spoken"], " ".join(x for x in (w["kinds"].get(r["kind"], r["kind"]), r["label"]) if x), where]
            )
        await self.show_card(AGENDA, w["agenda"], a2ui.table_tree([w["when"], w["what"], w["where"]], rows))

    async def list_changed(self, name: str) -> None:
        items = [{"text": r["item"], "done": bool(r["done"])} for r in self.store.list_items(name)]
        title = self.words["shopping"] if name == home.SHOPPING else f"{self.words['list']} {name}"
        await self.show_card(f"list-{name}", title, a2ui.list_tree(items, self.s.lang))

    async def memory_changed(self, show: bool = False) -> None:
        self._memory_told = None
        if not show and MEMORY not in self.cards:
            return
        w = self.words
        rows = [[m["about"], m["fact"]] for m in self.store.memories()]
        await self.show_card(MEMORY, w["memory"], a2ui.table_tree([w["about"], w["fact"]], rows))

    def missing(self, what: str, why: str) -> None:
        self.store.missing(self._turn_id, what, why)

    async def ring(self, item: dict[str, Any], late_min: int) -> None:
        w = self.words
        await self._send({"type": "ring", "id": item["id"], "kind": item["kind"], "label": item["label"]})
        head = {"timer": w["timer"], "alarm": w["kinds"]["alarm"]}.get(item["kind"], w["reminder"])
        text = f"{head}: {item['label']}." if item["label"] else f"{head}."
        if late_min > 0:
            text += " (" + w["late"].format(n=late_min) + ")"
        self.say(text)

    # ── confirmations ─────────────────────────────────────────────────────

    async def _ask_confirm(self, tool: str, args: dict[str, Any]) -> None:
        await self._send({"type": "a2ui", "messages": card(tool, args, self.s.a2ui_version)})
        self.say(self.words["confirm"])

    async def _close_confirm(self) -> None:
        msgs = a2ui.check([{"deleteSurface": {"surfaceId": a2ui.CONFIRM_SURFACE}}], self.s.a2ui_version)
        await self._send({"type": "a2ui", "messages": msgs})

    # ── the wire ───────────────────────────────────────────────────────────

    async def _send(self, data: dict[str, Any]) -> None:
        async with self._lock:
            with contextlib.suppress(Exception):
                await self.ws.send_text(json.dumps(data, ensure_ascii=False))

    async def _send_bytes(self, data: bytes) -> None:
        async with self._lock:
            with contextlib.suppress(Exception):
                await self.ws.send_bytes(data)

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
