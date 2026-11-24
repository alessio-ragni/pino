"""The full round on the websocket, with fake voice, ears and brain."""

import json

from fastapi.testclient import TestClient

from pino.app import create_app


class FakeEars:
    name = "fake"

    def __init__(self, text="Pino, che tempo fa?"):
        self.text = text

    async def transcribe(self, wav):
        return self.text


class FakeVoice:
    name = "fake"
    sample_rate = 24000

    async def speak(self, text):
        yield b"\x01\x00" * 10


def _tool(servers, server, name):
    """The handler of one of Pino's own tools, as Claude would call it."""
    from pino import a2ui, home

    session = servers["_session"]
    if server == "screen":
        tools = a2ui.tools(session, "it")
    else:
        tools = home.tools(session.store, session, "Europe/Rome")
    return next(t.handler for t in tools if t.name == name)


class FakeAgent:
    asked: list[str] = []

    def __init__(self, s, servers, gate, tracer):
        self.gate = gate
        self.tracer = tracer
        self.servers = {**servers, "_session": tracer}
        self.started_at = 0.0
        self.last_result = None

    async def start(self):
        pass

    async def stop(self):
        pass

    async def restart(self):
        pass

    async def interrupt(self):
        pass

    async def ask(self, text, on_text):
        FakeAgent.asked.append(text)
        text = text.rsplit("] ", 1)[-1]  # what was said, without the context line
        if "chiacchiere" in text:
            on_text("…")
            return "…"
        if "whatsapp" in text.lower():
            ok = await self.gate.decide("mcp__claude_ai_WhatsApp__send_message", {"text": "ciao"})
            on_text("Mandato." if ok else "Va bene, niente.")
            return "ok"
        if "carbonara" in text:
            on_text("[card:carbonara] Ecco la carbonara.")
            self.tracer.tool_started("t1", "mcp__screen__show_recipe", {}, True, None)
            show = _tool(self.servers, "screen", "show_recipe")
            await show(
                {
                    "card_id": "carbonara",
                    "title": "Carbonara",
                    "ingredients": [{"qty": "200 g", "name": "spaghetti"}],
                    "sections": [{"name": "Cottura", "steps": ["Bolli l'acqua", "Butta la pasta"]}],
                    "current_step": 1,
                }
            )
            self.tracer.tool_finished("t1", True)
            return "[card:carbonara] Ecco la carbonara."
        if "pecorino" in text:
            on_text("[card:carbonara] Cinquanta grammi.")
            return "[card:carbonara] Cinquanta grammi."
        if "sveglia" in text:
            alarm = _tool(self.servers, "home", "set_alarm")
            out = await alarm({"time": "07:00", "label": "Scuola"})
            on_text("[card:agenda] " + ("Non ci riesco." if out.get("is_error") else "Sveglia messa."))
            return "ok"
        if "latte" in text:
            add = _tool(self.servers, "home", "list_add")
            await add({"items": ["latte"]})
            on_text("[card:list-spesa] Fatto.")
            return "[card:list-spesa] Fatto."
        if "ricordati" in text:
            remember = _tool(self.servers, "home", "remember")
            await remember({"fact": "likes green", "about": "me"})
            on_text("[card:chat] Va bene.")
            return "[card:chat] Va bene."
        if "cosa sai" in text:
            await _tool(self.servers, "home", "memories")({})
            on_text("[card:memory] Ecco.")
            return "[card:memory] Ecco."
        on_text("[card:chat] Domani sole. ")
        on_text("Poche nuvole.")
        return "[card:chat] Domani sole. Poche nuvole."


def _messages(ws, *until):
    out = []
    while True:
        m = ws.receive()
        if "text" in m and m["text"]:
            data = json.loads(m["text"])
            out.append(data)
            if data["type"] in until:
                return out
        else:
            out.append({"type": "bytes"})


def _connect(ws):
    """ready, then the cards replay."""
    assert ws.receive_json()["type"] == "ready"
    assert ws.receive_json()["type"] == "cards_reset"


def _speak(ws, why=None):
    start = {"type": "start"}
    if why:
        start["why"] = why
    ws.send_json(start)
    ws.send_bytes(b"\x00\x00" * 16000)
    ws.send_json({"type": "end"})
    return _messages(ws, "done", "ignored")


def _app(settings, text="Pino, che tempo fa?"):
    return create_app(settings, stt=FakeEars(text), tts=FakeVoice(), agent_factory=FakeAgent, bell=False)


def test_voice_in_voice_out_and_the_journal(settings):
    app = _app(settings)
    with TestClient(app) as client:
        with client.websocket_connect("/ws?token=prova") as ws:
            _connect(ws)
            got = _speak(ws, "name")
            kinds = [m["type"] for m in got]
            assert kinds[0] == "heard" and "say" in kinds and "bytes" in kinds
            # The tag is never spoken.
            assert all("[card" not in m.get("text", "") for m in got)
            assert any(m["type"] == "card" and m["id"] == "chat" for m in got)
        turn = app.state.store.recent_turns()[0]
        assert turn["asked"] == "Pino, che tempo fa?" and turn["why"] == "name"
        assert turn["card"] == "chat" and turn["outcome"] == "ok"
        assert turn["ms_first_text"] is not None and turn["ms_first_audio"] is not None
    assert FakeAgent.asked[-1].startswith("[") and "open cards" in FakeAgent.asked[-1]


def test_without_the_name_everything_goes(settings):
    app = _app(settings, "la partita dura un'ora e mezza")
    with TestClient(app) as client:
        with client.websocket_connect("/ws?token=prova") as ws:
            _connect(ws)
            got = _speak(ws)  # without «why» the careful case holds: woken by the name
            assert got[-1] == {"type": "ignored", "reason": "non chiamato"}
            assert all(m["type"] != "heard" for m in got)
        store = app.state.store
        row = store.conn.execute("SELECT * FROM recordings").fetchone()
        assert row["transcript"] is None and row["path"] is None and row["error"] == "non chiamato"
        assert not list(settings.audio_dir.rglob("*.wav"))
        assert store.recent_turns() == []
        assert (
            store.conn.execute("SELECT kind, detail FROM events WHERE kind = 'ignored'").fetchone()[1] == "non chiamato"
        )


def test_with_the_button_no_name_needed(settings):
    with TestClient(_app(settings, "che tempo fa?")) as client:
        with client.websocket_connect("/ws?token=prova") as ws:
            _connect(ws)
            assert _speak(ws, "button")[-1]["type"] == "done"


def test_stop_ends_the_conversation(settings):
    with TestClient(_app(settings, "Pino, basta così")) as client:
        with client.websocket_connect("/ws?token=prova") as ws:
            _connect(ws)
            assert _speak(ws, "name")[-1] == {"type": "ignored", "reason": "stop"}


def test_in_the_follow_up_his_echo_goes(settings):
    ears = FakeEars("Pino, che tempo fa?")
    app = create_app(settings, stt=ears, tts=FakeVoice(), agent_factory=FakeAgent, bell=False)
    with TestClient(app) as client:
        with client.websocket_connect("/ws?token=prova") as ws:
            _connect(ws)
            _speak(ws, "name")
            ears.text = "Domani sole, poche nuvole."
            assert _speak(ws, "follow")[-1] == {"type": "ignored", "reason": "eco"}


def test_barge_without_the_name_is_his_echo(settings):
    with TestClient(_app(settings, "poche nuvole")) as client:
        with client.websocket_connect("/ws?token=prova") as ws:
            _connect(ws)
            assert _speak(ws, "barge")[-1] == {"type": "ignored", "reason": "eco"}


def test_in_the_follow_up_if_not_for_him_silent(settings):
    FakeAgent.asked = []
    app = _app(settings, "chiacchiere fra noi")
    with TestClient(app) as client:
        with client.websocket_connect("/ws?token=prova") as ws:
            _connect(ws)
            got = _speak(ws, "follow")
            assert got[-1] == {"type": "ignored", "reason": "non per me"}
            assert all(m["type"] != "say" for m in got)
        assert "[follow-up, no name] chiacchiere" in FakeAgent.asked[-1]
        row = app.state.store.conn.execute("SELECT * FROM recordings").fetchone()
        assert row["transcript"] is None


def test_a_recipe_card_then_a_question_on_it(settings):
    app = _app(settings, "Pino, la carbonara per due")
    with TestClient(app) as client:
        with client.websocket_connect("/ws?token=prova") as ws:
            _connect(ws)
            got = _speak(ws, "name")
            screen = [m for m in got if m["type"] == "a2ui"]
            assert screen[0]["messages"][0]["createSurface"]["surfaceId"] == "carbonara"
            assert {"type": "focus", "id": "carbonara"} in got
            ws.send_json({"type": "text", "text": "quanto pecorino?"})
            got = _messages(ws, "done")
            cards = [m for m in got if m["type"] == "card"]
            assert cards[-1]["id"] == "carbonara"
            assert [t["q"] for t in cards[-1]["thread"]] == ["Pino, la carbonara per due", "quanto pecorino?"]
            # The second time the surface is updated, not created again.
            assert not any(m["type"] == "a2ui" for m in got)
        store = app.state.store
        tools = store.conn.execute("SELECT tool, ok FROM tool_calls").fetchall()
        assert [tuple(t) for t in tools] == [("mcp__screen__show_recipe", 1)]
        # A new connection gets the cards back.
        with client.websocket_connect("/ws?token=prova") as ws:
            assert ws.receive_json()["type"] == "ready"
            assert ws.receive_json()["type"] == "cards_reset"
            meta = ws.receive_json()
            assert meta["type"] == "card" and meta["id"] == "carbonara"
            assert ws.receive_json()["type"] == "a2ui"
            ws.send_json({"type": "closed", "surfaceId": "carbonara"})
        assert store.cards_open("tablet") == []


def test_shopping_list_tool_draws_its_card(settings):
    with TestClient(_app(settings, "Pino, metti il latte")) as client:
        with client.websocket_connect("/ws?token=prova") as ws:
            _connect(ws)
            got = _speak(ws, "name")
            surfaces = [m["messages"][0] for m in got if m["type"] == "a2ui"]
            assert surfaces[0]["createSurface"]["surfaceId"] == "list-spesa"
            comps = [m for m in got if m["type"] == "a2ui"][0]["messages"][1]["updateComponents"]["components"]
            assert any(c.get("label") == "latte" for c in comps)


def test_the_confirmation_goes_through_the_voice(settings):
    with TestClient(_app(settings)) as client:
        with client.websocket_connect("/ws?token=prova") as ws:
            _connect(ws)
            ws.send_json({"type": "text", "text": "manda un whatsapp"})
            got = _messages(ws, "a2ui")
            assert got[-1]["messages"][0]["createSurface"]["surfaceId"] == "conferma"
            ws.send_json({"type": "text", "text": "sì"})
            got = _messages(ws, "done")
            assert any(m.get("text") == "Mandato." for m in got)


def test_no_token_nothing(settings):
    with TestClient(_app(settings)) as client:
        import pytest
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws?token=sbagliato") as ws:
                ws.receive_json()


def test_a_sentence_said_twice_is_said_once():
    from pino.session import repeats

    first = "Passo due: in una ciotola sbatti le uova intere, i tuorli, il pecorino e una generosa macinata di pepe."
    assert repeats("Siamo al passo due: sbatti insieme uova, tuorli, pecorino e pepe.", [first])
    assert not repeats("Fatto, latte e uova sono nella lista della spesa.", ["Aggiungo latte e uova alla spesa."])
    assert not repeats("Sì.", ["Sì."])  # too short to judge
    assert repeats("Secondo passo:", ["Secondo passo: sbattete in una ciotola i tuorli."])


def test_an_alarm_goes_to_the_tablet_clock(settings):
    with TestClient(_app(settings, "Pino, mettimi una sveglia alle sette")) as client:
        with client.websocket_connect("/ws?token=prova") as ws:
            _connect(ws)
            ws.send_json({"type": "start", "why": "name"})
            ws.send_bytes(b"\x00\x00" * 16000)
            ws.send_json({"type": "end"})
            device = next(m for m in _messages(ws, "device") if m["type"] == "device")
            assert device["action"] == "set_alarm" and device["hour"] == 7 and device["label"] == "Scuola"
            ws.send_json({"type": "device_result", "id": device["id"], "ok": True})
            got = _messages(ws, "done")
            assert any(m.get("text") == "Sveglia messa." for m in got)


def test_memory_reaches_claude_once_and_again_after_a_change(settings):
    FakeAgent.asked.clear()
    with TestClient(_app(settings, "Pino, che tempo fa?")) as client:
        with client.websocket_connect("/ws?token=prova") as ws:
            _connect(ws)
            _speak(ws, "name")
            assert "what you know: nothing yet" in FakeAgent.asked[-1]
            ws.send_json({"type": "text", "text": "ricordati che mi piace il verde"})
            _messages(ws, "done")
            assert "what you know" not in FakeAgent.asked[-1]
            ws.send_json({"type": "text", "text": "cosa sai di me?"})
            got = _messages(ws, "done")
            assert "#1 me: likes green" in FakeAgent.asked[-1]
            surfaces = [m["messages"][0] for m in got if m["type"] == "a2ui"]
            assert surfaces[0]["createSurface"]["surfaceId"] == "memory"
