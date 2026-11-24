"""The bell: rings timers and reminders when they are due.

Once a second it looks at the agenda. A due timer or reminder rings on a
connected tablet: a tone there and Pino's voice. It does not talk over a
conversation: it waits for the turn to end, at most `PATIENCE_S` seconds. With
no tablet connected the item waits and rings as soon as one comes back, saying
how late it is.

Alarms on the tablet's Clock app are not rung here: the Clock app rings them. When
their time passes, a one-off alarm is closed and a repeating one moves to its next
day. Alarms too far ahead for the Clock app ring here, like a timer.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Protocol

from pino.home import FMT, local_now
from pino.store import Store

log = logging.getLogger("pino.bell")

TICK_S = 1.0
PATIENCE_S = 30.0


class Ringer(Protocol):
    @property
    def busy(self) -> bool: ...

    async def ring(self, item: dict[str, Any], late_min: int) -> None: ...

    async def agenda_changed(self, show: bool = True) -> None: ...


def next_repeat(due: datetime, days: list[int]) -> datetime:
    for step in range(1, 8):
        candidate = due + timedelta(days=step)
        if candidate.isoweekday() in days:
            return candidate
    return due + timedelta(days=7)


async def ring_due(store: Store, tz: str, ringers: Callable[[], list[Ringer]], waiting: dict[int, float]) -> None:
    now = local_now(tz)
    for item in store.agenda_due(now.strftime(FMT)):
        due = datetime.strptime(item["due_at"], FMT)
        if item["kind"] == "alarm" and item["on_device"]:
            days = [int(d) for d in (item["repeat_days"] or "").split(",") if d]
            if days:
                store.agenda_move(item["id"], next_repeat(due, days).strftime(FMT))
            else:
                store.agenda_rang(item["id"])
                store.agenda_end(item["id"], "rang")
            continue
        targets = ringers()
        if not targets:
            continue
        loop = asyncio.get_running_loop().time()
        first = waiting.setdefault(item["id"], loop)
        free = [r for r in targets if not r.busy]
        if not free and loop - first < PATIENCE_S:
            continue
        waiting.pop(item["id"], None)
        store.agenda_rang(item["id"])
        store.agenda_end(item["id"], "rang")
        late = max(0, int((now - due).total_seconds() // 60))
        for r in free or targets[:1]:
            try:
                await r.ring(item, late)
                await r.agenda_changed(show=False)
            except Exception:  # noqa: BLE001 — a broken tablet must not stop the bell
                log.exception("ring failed")
        store.event("ring", {"id": item["id"], "kind": item["kind"], "late_min": late})


async def ring_forever(store: Store, tz: str, ringers: Callable[[], list[Ringer]]) -> None:
    waiting: dict[int, float] = {}
    while True:
        try:
            await ring_due(store, tz, ringers, waiting)
        except Exception:  # noqa: BLE001
            log.exception("bell tick failed")
        await asyncio.sleep(TICK_S)
