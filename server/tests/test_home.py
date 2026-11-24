"""Alarms, timers, reminders and lists: the tools Claude calls, and the bell that rings them."""

from datetime import datetime

import pytest

from pino import home
from pino.bell import next_repeat, ring_due
from pino.home import FMT, parse_when, spoken_when
from pino.store import Store


class FakeHost:
    def __init__(self, device_ok=True):
        self.device_ok = device_ok
        self.actions = []
        self.lists = []
        self.agenda = 0
        self.missed = []
        self.rung = []
        self.busy = False
        self.memory = []

    async def device_action(self, action):
        self.actions.append(action)
        return self.device_ok

    async def agenda_changed(self, show=True):
        self.agenda += 1

    async def list_changed(self, name):
        self.lists.append(name)

    async def memory_changed(self, show=False):
        self.memory.append(show)

    def missing(self, what, why):
        self.missed.append(what)

    async def ring(self, item, late_min):
        self.rung.append((item["kind"], item["label"], late_min))


def _tools(settings, host):
    store = Store(settings.db_path, settings.audio_dir)
    return store, {t.name: t.handler for t in home.tools(store, host, "Europe/Rome")}


def test_times():
    now = datetime(2026, 11, 15, 18, 0)
    assert parse_when("2026-11-16 07:00", now) == datetime(2026, 11, 16, 7, 0)
    assert parse_when("19:30", now) == datetime(2026, 11, 15, 19, 30)
    assert parse_when("07:00", now) == datetime(2026, 11, 16, 7, 0)  # already past: tomorrow
    with pytest.raises(ValueError):
        parse_when("domani", now)
    assert spoken_when(datetime(2026, 11, 16, 7, 0), now) == "domani alle 07:00"
    assert next_repeat(datetime(2026, 11, 14, 7, 0), [1]) == datetime(2026, 11, 16, 7, 0)  # Sat → Mon


async def test_alarm_goes_to_the_clock_and_the_agenda(settings):
    host = FakeHost()
    store, t = _tools(settings, host)
    out = await t["set_alarm"]({"time": "07:15", "label": "Scuola", "repeat": ["mon", "fri"]})
    assert not out.get("is_error")
    assert host.actions[0] == {"action": "set_alarm", "hour": 7, "minute": 15, "days": [1, 5], "label": "Scuola"}
    item = store.agenda_live()[0]
    assert item["kind"] == "alarm" and item["repeat_days"] == "1,5" and item["on_device"] == 1
    out = await t["cancel"]({"id": item["id"]})
    # Android cannot delete another app's alarm: the Clock app is opened for the person.
    assert host.actions[-1] == {"action": "show_alarms"} and "Clock app" in out["content"][0]["text"]
    assert store.agenda_live() == []


async def test_alarm_too_far_ahead_is_rung_by_pino(settings):
    host = FakeHost()
    store, t = _tools(settings, host)
    out = await t["set_alarm"]({"time": "2099-01-01 07:00"})
    assert "Pino rings it" in out["content"][0]["text"] and host.actions == []
    item = store.agenda_live()[0]
    assert item["on_device"] == 0
    store.agenda_move(item["id"], "2000-01-01 00:00:00")
    await ring_due(store, "Europe/Rome", lambda: [host], {})
    assert host.rung[0][0] == "alarm"


async def test_alarm_refused_by_the_tablet_is_not_written(settings):
    store, t = _tools(settings, FakeHost(device_ok=False))
    out = await t["set_alarm"]({"time": "07:00"})
    assert out["is_error"] and store.agenda_live() == []


async def test_timer_rings_and_ends(settings):
    host = FakeHost()
    store, t = _tools(settings, host)
    await t["set_timer"]({"minutes": 0.01, "label": "pasta"})
    item = store.agenda_live()[0]
    store.agenda_move(item["id"], "2000-01-01 00:00:00")  # already due
    await ring_due(store, "Europe/Rome", lambda: [host], {})
    assert host.rung[0][:2] == ("timer", "pasta") and host.rung[0][2] > 0
    assert store.agenda_live() == [] and store.agenda_get(item["id"])["ended_how"] == "rang"


async def test_the_bell_waits_while_he_is_talking(settings):
    host = FakeHost()
    host.busy = True
    store, t = _tools(settings, host)
    await t["set_reminder"]({"time": "2000-01-01 10:00", "text": "chiamare"})
    await ring_due(store, "Europe/Rome", lambda: [host], {})
    assert host.rung == [] and len(store.agenda_live()) == 1


async def test_without_a_tablet_it_waits(settings):
    store, t = _tools(settings, FakeHost())
    await t["set_reminder"]({"time": "2000-01-01 10:00", "text": "chiamare"})
    await ring_due(store, "Europe/Rome", lambda: [], {})
    assert len(store.agenda_live()) == 1


async def test_repeating_alarm_moves_to_its_next_day(settings):
    store = Store(settings.db_path, settings.audio_dir)
    rid = store.agenda_add("alarm", "2000-01-03 07:00:00", "x", "1", on_device=True)  # a Monday
    await ring_due(store, "Europe/Rome", lambda: [], {})
    assert store.agenda_get(rid)["due_at"] == datetime(2000, 1, 10, 7, 0).strftime(FMT)


async def test_shopping_list(settings):
    host = FakeHost()
    store, t = _tools(settings, host)
    await t["list_add"]({"items": ["latte", "Pane", "latte"]})
    assert [r["item"] for r in store.list_items("spesa")] == ["latte", "Pane"]
    await t["list_remove"]({"items": ["pane"], "done": True})
    assert [(r["item"], r["done"]) for r in store.list_items("spesa")] == [("latte", 0), ("Pane", 1)]
    out = await t["list_remove"]({"items": ["uova"]})
    assert "uova" in out["content"][0]["text"]
    await t["list_show"]({"clear": True, "only_done": True})
    assert [r["item"] for r in store.list_items("spesa")] == ["latte"]
    assert host.lists == ["spesa"] * 4


async def test_missing_tool_is_logged(settings):
    host = FakeHost()
    _, t = _tools(settings, host)
    await t["report_missing"]({"what": "accendere la luce"})
    assert host.missed == ["accendere la luce"]


async def test_memory_is_written_silently_and_never_deleted(settings):
    host = FakeHost()
    store, t = _tools(settings, host)
    out = await t["remember"]({"fact": "carbonara with parmigiano, no pecorino", "about": "a friend"})
    assert "#1" in out["content"][0]["text"]
    await t["remember"]({"fact": "carbonara with parmigiano, no pecorino", "about": "a friend"})
    assert len(store.memories()) == 1  # the same thing twice is one memory
    await t["remember"]({"fact": "likes green", "about": "me"})
    await t["remember"]({"fact": "likes blue", "about": "me", "replaces": 2})
    assert [m["fact"] for m in store.memories()] == ["carbonara with parmigiano, no pecorino", "likes blue"]
    await t["forget"]({"id": 1, "why": "no longer true"})
    assert [m["fact"] for m in store.memories()] == ["likes blue"]
    ended = store._rows("SELECT ended_why FROM memories WHERE ended_at IS NOT NULL ORDER BY id")
    assert [r["ended_why"] for r in ended] == ["no longer true", "corrected"]
    assert (await t["forget"]({"id": 1})).get("is_error")
    out = await t["memories"]({})
    assert "likes blue" in out["content"][0]["text"]
    assert host.memory == [False, False, False, False, False, True]
