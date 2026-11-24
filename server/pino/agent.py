"""The brain: Claude Code through the Agent SDK, with the subscription login.

It runs with the host's user settings, so it sees the same claude.ai connectors,
but with hooks off and in an empty folder of its own. Of the built-in tools only
web search and reading a page remain: no shell, no files.

Speed matters more than anything for a voice, so:

* one Claude Code process per connected tablet, kept warm and reused;
* only the household connectors stay on (`PINO_CONNECTORS`); every other
  MCP server is switched off after connecting, so its tool descriptions do not
  weigh on every request;
* no extended thinking, low effort;
* the session restarts after a quiet spell (`PINO_IDLE_RESET_MIN`), so the
  conversation does not grow forever. What matters (the open cards, the time)
  travels with every question anyway.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from pino.config import Settings

log = logging.getLogger("pino.agent")

PROMPT = Path(__file__).parent / "prompts" / "character.md"
OWN = ("screen", "home")

# Tools of the household connectors a voice never needs. Each description is sent with every
# request: dropping these took the connectors from about 54k tokens to about 32k (Gmail alone
# was 30k), and every answer starts that much sooner.
UNUSED_TOOLS = [
    *(
        f"mcp__claude_ai_Gmail__{t}"
        for t in (
            "apply_sensitive_message_label apply_sensitive_thread_label create_label delete_draft delete_label "
            "download_gmail_attachment forward get_draft label_message label_thread list_drafts list_labels "
            "mark_message_spam mark_thread_spam trash_message trash_thread unlabel_message unlabel_thread "
            "unmark_message_spam unmark_thread_spam untrash_message untrash_thread update_draft update_label "
            "update_message_labels"
        ).split()
    ),
    *(
        f"mcp__claude_ai_Google_Drive__{t}"
        for t in (
            "copy_file create_file download_file_content get_file_permissions get_shared_drive_metadata "
            "list_file_revisions list_shared_drives share_file trash_file update_file"
        ).split()
    ),
]


def system_prompt(s: Settings) -> str:
    return PROMPT.read_text(encoding="utf-8")


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower().removeprefix("claude.ai").removeprefix("claude_ai"))


def keep_server(name: str, connectors: tuple[str, ...]) -> bool:
    """Pino's own servers and the household connectors stay; everything else goes."""
    if name in OWN:
        return True
    n = _norm(name)
    return any(_norm(c) and _norm(c) == n for c in connectors)


class Tracer(Protocol):
    def tool_started(
        self, tool_use_id: str, tool: str, tool_input: Any, allowed: bool, confirmed: str | None
    ) -> None: ...

    def tool_finished(self, tool_use_id: str, ok: bool, error: str | None = None) -> None: ...


class Agent:
    def __init__(self, s: Settings, servers: dict[str, Any], gate, tracer: Tracer | None = None) -> None:
        self.s = s
        self.servers = servers
        self.gate = gate
        self.tracer = tracer
        self.client = None
        self.last_result: Any = None
        self.started_at = 0.0
        self.kept: list[str] = []
        self.dropped: list[str] = []
        self._trimming: asyncio.Task | None = None
        # A question never meets a brain halfway through a restart: both take this in turn.
        self._busy = asyncio.Lock()

    async def _pre(self, data: dict[str, Any], tool_use_id: str | None, context: Any):
        out = await self.gate.pre_tool_use(data, tool_use_id, context)
        if self.tracer is not None:
            allowed = out["hookSpecificOutput"]["permissionDecision"] == "allow"
            self.tracer.tool_started(
                str(tool_use_id or data.get("tool_use_id") or ""),
                str(data.get("tool_name", "")),
                data.get("tool_input"),
                allowed,
                self.gate.last_how,
            )
        return out

    async def _post(self, data: dict[str, Any], tool_use_id: str | None, context: Any):
        if self.tracer is not None:
            response = data.get("tool_response")
            failed = isinstance(response, dict) and bool(response.get("is_error"))
            self.tracer.tool_finished(
                str(tool_use_id or data.get("tool_use_id") or ""),
                not failed,
                str(response)[:500] if failed else None,
            )
        return {}

    async def _failed(self, data: dict[str, Any], tool_use_id: str | None, context: Any):
        if self.tracer is not None:
            self.tracer.tool_finished(
                str(tool_use_id or data.get("tool_use_id") or ""), False, str(data.get("error", ""))[:500]
            )
        return {}

    async def start(self) -> None:
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher

        if os.environ.get("ANTHROPIC_API_KEY"):
            log.warning("ANTHROPIC_API_KEY is set: the CLI will bill the key, not the subscription.")
        self.s.work_dir.mkdir(parents=True, exist_ok=True)
        options = ClaudeAgentOptions(
            system_prompt=system_prompt(self.s),
            model=self.s.model,
            effort=self.s.effort or None,
            thinking={"type": "disabled"},
            tools=["WebSearch", "WebFetch"],
            disallowed_tools=UNUSED_TOOLS,
            mcp_servers=self.servers,
            setting_sources=["user"],
            settings='{"disableAllHooks": true}',
            hooks={
                "PreToolUse": [HookMatcher(matcher=None, hooks=[self._pre])],
                "PostToolUse": [HookMatcher(matcher=None, hooks=[self._post])],
                "PostToolUseFailure": [HookMatcher(matcher=None, hooks=[self._failed])],
            },
            include_partial_messages=True,
            cwd=str(self.s.work_dir),
            # Conversations are not saved on disk: Pino does not resume them, and what is said
            # at home does not stay in Claude Code's files.
            extra_args={"no-session-persistence": None},
        )
        t0 = time.monotonic()
        self.client = ClaudeSDKClient(options=options)
        await self.client.connect()
        self.started_at = time.monotonic()
        # The claude.ai connectors show up a few seconds after connecting: they are trimmed as they come.
        self._trimming = asyncio.create_task(self._trim_while_loading())
        log.info("brain ready in %.1f s", self.started_at - t0)

    async def _trim_while_loading(self, patience_s: float = 15) -> None:
        deadline = time.monotonic() + patience_s
        while time.monotonic() < deadline:
            settled = await self._trim_servers()
            if settled:
                break
            await asyncio.sleep(0.5)
        log.info("connectors kept: %s; switched off: %s", ", ".join(self.kept), ", ".join(self.dropped) or "none")

    async def _trim_servers(self) -> bool:
        """Switches off every MCP server that is neither Pino's nor a household connector.

        True once nothing is still loading (and at least the claude.ai connectors have appeared).
        """
        try:
            status = await self.client.get_mcp_status()
        except Exception:  # noqa: BLE001 — an older CLI: keep everything rather than fail
            log.warning("cannot read MCP status: all connectors stay on")
            return True
        servers = status.get("mcpServers", [])
        for server in servers:
            name = server.get("name", "")
            if keep_server(name, self.s.connectors):
                if name not in self.kept:
                    self.kept.append(name)
                continue
            if server.get("status") == "disabled" or name in self.dropped:
                continue
            try:
                await self.client.toggle_mcp_server(name, False)
                self.dropped.append(name)
            except Exception as bad:  # noqa: BLE001
                log.warning("cannot switch off %s: %s", name, bad)
        pending = [
            s for s in servers if s.get("status") == "pending" and keep_server(s.get("name", ""), self.s.connectors)
        ]
        claudeai = any(s.get("scope") == "claudeai" for s in servers)
        return claudeai and not pending

    async def context_tokens(self) -> dict[str, Any] | None:
        try:
            usage = await self.client.get_context_usage()
        except Exception:  # noqa: BLE001
            return None
        return {"total": usage.get("totalTokens"), "categories": usage.get("categories")}

    async def stop(self) -> None:
        if self._trimming is not None:
            self._trimming.cancel()
        if self.client is not None:
            await self.client.disconnect()
            self.client = None

    async def restart(self) -> None:
        async with self._busy:
            await self.stop()
            await self.start()

    async def interrupt(self) -> None:
        if self.client is not None:
            await self.client.interrupt()

    async def ask(self, text: str, on_text: Callable[[str], None]) -> str:
        """Sends the sentence to Claude and passes the pieces of the answer to `on_text` as they come."""
        async with self._busy:
            return await self._ask(text, on_text)

    async def _ask(self, text: str, on_text: Callable[[str], None]) -> str:
        from claude_agent_sdk import AssistantMessage, ResultMessage, StreamEvent, TextBlock

        assert self.client is not None, "start() before ask()"
        if self._trimming is not None and not self._trimming.done():
            # Better wait a moment than send every connector's tools with the first question.
            with contextlib.suppress(Exception):
                await self._trimming
        self.last_result = None
        await self.client.query(text)
        streamed: list[str] = []
        whole: list[str] = []
        async for message in self.client.receive_response():
            if isinstance(message, StreamEvent):
                ev = message.event
                if ev.get("type") == "content_block_start" and streamed:
                    # A new text block after a tool: it is another sentence.
                    if ev.get("content_block", {}).get("type") == "text":
                        on_text("\n")
                elif ev.get("type") == "content_block_delta":
                    delta = ev.get("delta", {})
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        streamed.append(delta["text"])
                        on_text(delta["text"])
            elif isinstance(message, AssistantMessage):
                whole.extend(b.text for b in message.content if isinstance(b, TextBlock))
            elif isinstance(message, ResultMessage):
                self.last_result = message
        if not streamed and whole:
            # No streamed pieces (it happens): say it all at the end.
            for piece in whole:
                on_text(piece + "\n")
        return "".join(streamed) if streamed else "\n".join(whole)
