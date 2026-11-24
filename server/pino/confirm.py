"""Outward actions ask for permission, until you tell it to stop asking.

Every time Claude wants to use a tool it passes here. If the tool sends something
out (a WhatsApp, an email, an event) and that tool is not already trusted, the
call stops: the screen shows what it is about to do, the voice asks «lo faccio?»,
and it waits for a «sì», a «no», or a «non chiedermelo più» (by voice or button).
«Non chiedermelo più» holds for that tool, stays written down, and can be revoked.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pino.a2ui import CONFIRM_SURFACE
from pino.store import Store

Answer = Literal["yes", "always", "no"]

# Careful by construction: every external tool asks, EXCEPT those whose name clearly
# says they only read. The opposite (listing the verbs that send) broke twice in the
# first trial: connectors have English and Italian names («calendario_crea»), and one
# missing verb means an action that left without asking.
_READ_ONLY = {
    "search",
    "list",
    "get",
    "read",
    "find",
    "fetch",
    "download",
    "transcribe",
    "suggest",
    "query",
    "guide",
    "whoami",
    "status",
    "describe",
    "explore",
    "show",
    "analyze",
    "balance",
    "cerca",
    "leggi",
    "elenca",
    "oggi",
    "dammi",
    "istruzioni",
    "chi",
}
# A draft does not leave on its own.
_DRAFT = {"draft", "drafts", "bozza", "bozze"}

_ALWAYS = re.compile(r"\bnon\s+(me\s+lo\s+|mi\s+)?chieder(lo|melo|mi)\s+più\b|\bsempre\b|\bdon'?t\s+ask\b", re.I)
_NO = re.compile(r"^\s*(no|non\b|annulla|lascia\s+stare|aspetta|fermo|ferma|stop|cancel)", re.I)
_YES = re.compile(r"^\s*(sì|si|ok|okay|vai|manda|mandalo|mandala|certo|procedi|conferma|fallo|yes|sure|go)", re.I)

# Pino's own tools: the screen and the household (alarms, lists). They never go out.
OWN_SERVERS = ("mcp__screen__", "mcp__home__")


def is_outward(tool: str) -> bool:
    if not tool.startswith("mcp__") or tool.startswith(OWN_SERVERS):
        return False
    words = set(re.split(r"[_\W]+", tool.rsplit("__", 1)[-1].lower()))
    if "send" in words or "invia" in words or "manda" in words:
        return True
    return not (words & _READ_ONLY or words & _DRAFT)


def read_answer(text: str) -> Answer | None:
    if _ALWAYS.search(text):
        return "always"
    if _NO.search(text):
        return "no"
    if _YES.search(text):
        return "yes"
    return None


def label(tool: str) -> str:
    """«mcp__claude_ai_WhatsApp__send_message» → «WhatsApp · send message»."""
    parts = tool.split("__")
    service = parts[1].removeprefix("claude_ai_").replace("_", " ") if len(parts) > 2 else tool
    return f"{service} · {parts[-1].replace('_', ' ')}"


Ask = Callable[[str, dict[str, Any]], Awaitable[None]]
Close = Callable[[], Awaitable[None]]


class Gate:
    """The gate in front of every tool, with the wait for the answer."""

    def __init__(self, store: Store, ask: Ask, timeout_s: float = 120, close: Close | None = None) -> None:
        self.store = store
        self.ask = ask
        self.close = close
        self.timeout_s = timeout_s
        self._waiting: asyncio.Future[Answer] | None = None
        self.pending_tool: str | None = None
        # How the last asked tool was decided: yes | always | no | timeout. None if not asked.
        self.last_how: str | None = None

    @property
    def pending(self) -> bool:
        return self._waiting is not None and not self._waiting.done()

    def answer(self, answer: Answer) -> bool:
        if not self.pending:
            return False
        assert self._waiting is not None
        self._waiting.set_result(answer)
        return True

    async def decide(self, tool: str, args: dict[str, Any]) -> bool:
        """True if the tool may go. Outward actions wait for the answer."""
        self.last_how = None
        if not is_outward(tool) or self.store.trusted(tool):
            return True

        self._waiting = asyncio.get_running_loop().create_future()
        self.pending_tool = tool
        how: str
        try:
            await self.ask(tool, args)
            got: Answer = await asyncio.wait_for(self._waiting, timeout=self.timeout_s)
            how = got
        except TimeoutError:
            got, how = "no", "timeout"
            # Nobody answered: the card leaves the screen, otherwise it stays there forever.
            if self.close is not None:
                await self.close()
        finally:
            self._waiting = None
            self.pending_tool = None

        self.last_how = how
        if got == "always":
            self.store.grant(tool)
        return got in ("yes", "always")

    async def pre_tool_use(self, data: dict[str, Any], tool_use_id: str | None, context: Any):
        """The Agent SDK PreToolUse hook.

        A hook and not `can_use_tool`, on purpose: `can_use_tool` is only called
        when Claude Code would ask for permission, and with the host's settings
        ("auto" mode, "allow" rules) it almost never asks. The hook runs for
        every tool, always.
        """
        ok = await self.decide(str(data.get("tool_name", "")), dict(data.get("tool_input") or {}))
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow" if ok else "deny",
                "permissionDecisionReason": ("" if ok else "The person said no, or did not answer. Do not do it."),
            }
        }


def card(tool: str, args: dict[str, Any], version: str) -> list[dict]:
    """The confirmation card, built here and not by Claude: it must always be the same and honest."""
    lines = []
    for key, value in args.items():
        shown = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        lines.append(f"{key}: {shown[:400]}")
    from pino.a2ui import check

    sid = CONFIRM_SURFACE
    comps = [
        {"id": "root", "component": "Card", "child": "col"},
        {"id": "col", "component": "Column", "children": ["title", "body", "buttons"]},
        {"id": "title", "component": "Text", "text": f"Lo faccio? — {label(tool)}", "variant": "h3"},
        {"id": "body", "component": "Text", "text": "\n\n".join(lines) or "(nessun dettaglio)"},
        {"id": "buttons", "component": "Row", "children": ["yes", "always", "no"]},
        {"id": "yes_t", "component": "Text", "text": "Sì"},
        {"id": "always_t", "component": "Text", "text": "Non chiedermelo più"},
        {"id": "no_t", "component": "Text", "text": "No"},
        {
            "id": "yes",
            "component": "Button",
            "child": "yes_t",
            "variant": "primary",
            "action": {"event": {"name": "confirm_yes"}},
        },
        {"id": "always", "component": "Button", "child": "always_t", "action": {"event": {"name": "confirm_always"}}},
        {
            "id": "no",
            "component": "Button",
            "child": "no_t",
            "variant": "borderless",
            "action": {"event": {"name": "confirm_no"}},
        },
    ]
    return check(
        [{"createSurface": {"surfaceId": sid}}, {"updateComponents": {"surfaceId": sid, "components": comps}}],
        version,
    )


ACTIONS: dict[str, Answer] = {"confirm_yes": "yes", "confirm_always": "always", "confirm_no": "no"}
