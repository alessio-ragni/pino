import asyncio

from pino.confirm import Gate, card, is_outward, read_answer
from pino.store import Store

WA = "mcp__claude_ai_WhatsApp__send_message"


def test_what_goes_out():
    assert is_outward(WA)
    assert is_outward("mcp__claude_ai_Google_Calendar__create_event")
    assert is_outward("mcp__claude_ai_Gmail__send_message")
    assert not is_outward("mcp__claude_ai_Gmail__create_draft")
    assert not is_outward("mcp__claude_ai_WhatsApp__search_contacts")
    assert not is_outward("mcp__claude_ai_WhatsApp__list_chats")
    assert not is_outward("mcp__screen__show_recipe")
    assert not is_outward("mcp__home__set_alarm")
    assert not is_outward("WebSearch")
    # Italian names, and tools never seen: when in doubt it asks
    assert is_outward("mcp__drive__calendario_crea")
    assert is_outward("mcp__drive__calendario_elimina")
    assert is_outward("mcp__qualcosa__fai_una_cosa_nuova")
    assert not is_outward("mcp__drive__calendario_cerca")
    assert not is_outward("mcp__drive__posta_bozza")
    assert not is_outward("mcp__drive__istruzioni")


def test_the_answers():
    assert read_answer("Sì, mandalo") == "yes"
    assert read_answer("si") == "yes"
    assert read_answer("no lascia stare") == "no"
    assert read_answer("non chiedermelo più") == "always"
    assert read_answer("ok, e non me lo chiedere più") is not None
    assert read_answer("che ore sono?") is None


def _gate(settings, asked):
    store = Store(settings.db_path, settings.audio_dir)

    async def ask(tool, args):
        asked.append(tool)

    return Gate(store, ask, timeout_s=1), store


async def test_asks_and_waits_for_yes(settings):
    asked = []
    gate, _ = _gate(settings, asked)
    task = asyncio.create_task(gate.decide(WA, {"text": "ciao"}))
    await asyncio.sleep(0.01)
    assert gate.pending and asked == [WA]
    gate.answer("yes")
    assert await task is True


async def test_no_answer_is_a_no(settings):
    gate, _ = _gate(settings, [])
    assert await gate.decide(WA, {}) is False


async def test_dont_ask_again_is_remembered_and_revoked(settings):
    asked = []
    gate, store = _gate(settings, asked)
    task = asyncio.create_task(gate.decide(WA, {}))
    await asyncio.sleep(0.01)
    gate.answer("always")
    assert await task is True
    assert await gate.decide(WA, {}) is True
    assert asked == [WA]
    store.revoke(WA)
    assert not store.trusted(WA)
    assert store.trust_list()[0]["revoked_at"]


async def test_reads_pass_without_asking(settings):
    asked = []
    gate, _ = _gate(settings, asked)
    assert await gate.decide("mcp__claude_ai_Gmail__search_threads", {}) is True
    assert asked == []


def test_the_confirm_card_is_valid_a2ui():
    msgs = card(WA, {"recipient": "Contatto di prova", "text": "Arrivo"}, "v0.9.1")
    assert msgs[0]["createSurface"]["catalogId"]
    assert any(c["id"] == "root" for c in msgs[1]["updateComponents"]["components"])


async def test_the_hook_says_allow_or_deny(settings):
    gate, _ = _gate(settings, [])
    out = await gate.pre_tool_use({"tool_name": WA, "tool_input": {}}, None, None)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    out = await gate.pre_tool_use({"tool_name": "WebSearch", "tool_input": {}}, None, None)
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
