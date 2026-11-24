"""What stays written down: recordings, exchanges, the journal, cards, agenda, lists, trust.

One SQLite file on the server and nothing more. Audio files sit on disk next to
it, one per recording, and are deleted after `PINO_AUDIO_DAYS` days: the
transcript stays, and the row says when the audio was removed.

The journal (`turns`, `tool_calls`, `events`, `missing_tools`) is what lets
anyone ask afterwards "what happened this morning, how long did it take, which
tools did it use, what was it missing". Nothing in it is ever deleted.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pino.audio import INPUT_RATE, seconds, to_wav

SCHEMA = """
CREATE TABLE IF NOT EXISTS recordings (
  id          INTEGER PRIMARY KEY,
  at          TEXT NOT NULL,              -- UTC, ISO
  device      TEXT NOT NULL,
  seconds     REAL NOT NULL,
  path        TEXT,                       -- NULL once purged
  transcript  TEXT,
  engine      TEXT,
  error       TEXT,
  purged_at   TEXT
);
CREATE TABLE IF NOT EXISTS exchanges (
  id            INTEGER PRIMARY KEY,
  at            TEXT NOT NULL,
  device        TEXT NOT NULL,
  recording_id  INTEGER REFERENCES recordings(id),
  asked         TEXT NOT NULL,
  answered      TEXT NOT NULL,
  ms            INTEGER,
  error         TEXT
);
CREATE TABLE IF NOT EXISTS trust (
  tool        TEXT PRIMARY KEY,           -- full tool name, e.g. mcp__claude_ai_WhatsApp__send_message
  granted_at  TEXT NOT NULL,
  revoked_at  TEXT                        -- a revoked permission stays written down
);

-- One row per question: why it started, every timing, the model's bill.
CREATE TABLE IF NOT EXISTS turns (
  id               INTEGER PRIMARY KEY,
  at               TEXT NOT NULL,
  device           TEXT NOT NULL,
  why              TEXT,                  -- name | follow | button | key | barge | text | action
  recording_id     INTEGER REFERENCES recordings(id),
  asked            TEXT,
  answered         TEXT,
  card             TEXT,                  -- the card the answer belongs to
  model            TEXT,
  ms_transcribe    INTEGER,               -- end of speech → text
  ms_first_text    INTEGER,               -- text → first word from Claude
  ms_first_audio   INTEGER,               -- text → first sound sent to the tablet
  ms_total         INTEGER,               -- text → last word said
  api_ms           INTEGER,
  num_turns        INTEGER,
  input_tokens     INTEGER,
  output_tokens    INTEGER,
  cache_read_tokens INTEGER,
  cost_usd         REAL,                  -- what it would cost on the API; on the subscription it is quota
  outcome          TEXT,                  -- ok | interrupted | error | silent
  error            TEXT
);
CREATE TABLE IF NOT EXISTS tool_calls (
  id           INTEGER PRIMARY KEY,
  turn_id      INTEGER REFERENCES turns(id),
  at           TEXT NOT NULL,
  tool         TEXT NOT NULL,
  input        TEXT,
  ms           INTEGER,
  ok           INTEGER,
  error        TEXT,
  confirmed    TEXT                       -- NULL (not asked) | yes | always | no | timeout
);
CREATE TABLE IF NOT EXISTS events (
  id       INTEGER PRIMARY KEY,
  at       TEXT NOT NULL,
  device   TEXT,
  kind     TEXT NOT NULL,                 -- ignored | stop | render_error | connect | disconnect | ring | barge | agent
  detail   TEXT
);
CREATE TABLE IF NOT EXISTS missing_tools (
  id       INTEGER PRIMARY KEY,
  at       TEXT NOT NULL,
  turn_id  INTEGER REFERENCES turns(id),
  what     TEXT NOT NULL,
  why      TEXT
);

-- The cards on the tablet: one per topic, with its last picture and the short thread.
CREATE TABLE IF NOT EXISTS cards (
  device      TEXT NOT NULL,
  id          TEXT NOT NULL,
  title       TEXT NOT NULL,
  snapshot    TEXT,                       -- JSON: the A2UI messages that redraw it from nothing
  thread      TEXT NOT NULL DEFAULT '[]', -- JSON: [{"q":..., "a":...}], the last few
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL,
  closed_at   TEXT,
  PRIMARY KEY (device, id)
);

-- Alarms, timers and reminders. Nothing is deleted: an item ends with ended_at.
CREATE TABLE IF NOT EXISTS agenda (
  id          INTEGER PRIMARY KEY,
  kind        TEXT NOT NULL,              -- alarm | timer | reminder
  due_at      TEXT NOT NULL,              -- local time, YYYY-MM-DD HH:MM:SS (stays 7:00 across DST)
  label       TEXT NOT NULL DEFAULT '',
  repeat_days TEXT,                       -- alarms only: e.g. "1,2,3,4,5" (Mon=1)
  on_device   INTEGER NOT NULL DEFAULT 0,  -- 1: the tablet's Clock app rings it, not Pino
  created_at  TEXT NOT NULL,
  rang_at     TEXT,
  ended_at    TEXT,
  ended_how   TEXT                        -- rang | stopped | cancelled
);
CREATE INDEX IF NOT EXISTS agenda_live ON agenda (ended_at, due_at);

-- What Pino knows about the person it belongs to and their people. Nothing is deleted: a memory
-- that is wrong or no longer true ends with ended_at and the reason; a correction is a new row.
CREATE TABLE IF NOT EXISTS memories (
  id          INTEGER PRIMARY KEY,
  about       TEXT NOT NULL DEFAULT '',  -- who or what it is about: "me", a person, a place
  fact        TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  ended_at    TEXT,
  ended_why   TEXT
);

CREATE TABLE IF NOT EXISTS list_items (
  id          INTEGER PRIMARY KEY,
  list_name   TEXT NOT NULL,
  item        TEXT NOT NULL,
  done        INTEGER NOT NULL DEFAULT 0,
  added_at    TEXT NOT NULL,
  removed_at  TEXT
);
"""


def _now() -> datetime:
    return datetime.now(UTC)


def _iso() -> str:
    return _now().isoformat()


class Store:
    def __init__(self, db_path: Path, audio_dir: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        audio_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir = audio_dir
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self._lock = threading.Lock()
        self._migrate()

    def _migrate(self) -> None:
        """Columns added after a table already existed on a server."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(agenda)")}
        if "on_device" not in cols:
            self.conn.execute("ALTER TABLE agenda ADD COLUMN on_device INTEGER NOT NULL DEFAULT 0")
            self.conn.commit()

    def _write(self, sql: str, args: tuple = ()) -> int:
        with self._lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return int(cur.lastrowid or 0)

    def _rows(self, sql: str, args: tuple = ()) -> list[dict]:
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    # ── recordings ─────────────────────────────────────────────────────────

    def save_recording(self, pcm: bytes, device: str, rate: int = INPUT_RATE) -> int:
        at = _now()
        rid = self._write(
            "INSERT INTO recordings (at, device, seconds) VALUES (?, ?, ?)",
            (at.isoformat(), device, seconds(pcm, rate)),
        )
        folder = self.audio_dir / at.strftime("%Y-%m-%d")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{rid}.wav"
        path.write_bytes(to_wav(pcm, rate))
        self._write("UPDATE recordings SET path = ? WHERE id = ?", (str(path), rid))
        return rid

    def set_transcript(self, rid: int, text: str | None, engine: str, error: str | None = None) -> None:
        self._write(
            "UPDATE recordings SET transcript = ?, engine = ?, error = ? WHERE id = ?",
            (text, engine, error, rid),
        )

    def forget_recording(self, rid: int, reason: str) -> None:
        """A recording that was not for Pino: audio and text go, only the fact it happened stays."""
        row = self.conn.execute("SELECT path FROM recordings WHERE id = ?", (rid,)).fetchone()
        if row and row["path"]:
            Path(row["path"]).unlink(missing_ok=True)
        self._write(
            "UPDATE recordings SET path = NULL, transcript = NULL, error = ?, purged_at = ? WHERE id = ?",
            (reason, _iso(), rid),
        )

    def purge(self, days: int, now: datetime | None = None) -> int:
        """Deletes audio older than `days` days. The text stays."""
        limit = ((now or _now()) - timedelta(days=days)).isoformat()
        rows = self.conn.execute(
            "SELECT id, path FROM recordings WHERE path IS NOT NULL AND at < ?", (limit,)
        ).fetchall()
        stamp = (now or _now()).isoformat()
        for row in rows:
            Path(row["path"]).unlink(missing_ok=True)
            self._write("UPDATE recordings SET path = NULL, purged_at = ? WHERE id = ?", (stamp, row["id"]))
        return len(rows)

    # ── exchanges (kept for the history before the journal existed) ───────

    def log_exchange(
        self,
        device: str,
        asked: str,
        answered: str,
        ms: int,
        recording_id: int | None = None,
        error: str | None = None,
    ) -> None:
        self._write(
            "INSERT INTO exchanges (at, device, recording_id, asked, answered, ms, error) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_iso(), device, recording_id, asked, answered, ms, error),
        )

    # ── journal ────────────────────────────────────────────────────────────

    def start_turn(self, device: str, why: str, asked: str, recording_id: int | None, model: str) -> int:
        return self._write(
            "INSERT INTO turns (at, device, why, asked, recording_id, model) VALUES (?, ?, ?, ?, ?, ?)",
            (_iso(), device, why, asked, recording_id, model),
        )

    def finish_turn(self, turn_id: int, **fields: Any) -> None:
        allowed = {
            "answered",
            "card",
            "ms_transcribe",
            "ms_first_text",
            "ms_first_audio",
            "ms_total",
            "api_ms",
            "num_turns",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cost_usd",
            "outcome",
            "error",
        }
        keys = [k for k in fields if k in allowed]
        if not keys:
            return
        sets = ", ".join(f"{k} = ?" for k in keys)
        self._write(f"UPDATE turns SET {sets} WHERE id = ?", (*[fields[k] for k in keys], turn_id))

    def log_tool(
        self,
        turn_id: int | None,
        tool: str,
        tool_input: Any,
        ms: int | None,
        ok: bool,
        error: str | None = None,
        confirmed: str | None = None,
    ) -> int:
        shown = tool_input if isinstance(tool_input, str) else json.dumps(tool_input, ensure_ascii=False)
        return self._write(
            "INSERT INTO tool_calls (turn_id, at, tool, input, ms, ok, error, confirmed)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (turn_id, _iso(), tool, shown[:4000], ms, int(ok), error, confirmed),
        )

    def event(self, kind: str, detail: Any = None, device: str | None = None) -> None:
        text = detail if detail is None or isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)
        self._write("INSERT INTO events (at, device, kind, detail) VALUES (?, ?, ?, ?)", (_iso(), device, kind, text))

    def missing(self, turn_id: int | None, what: str, why: str | None) -> None:
        self._write(
            "INSERT INTO missing_tools (at, turn_id, what, why) VALUES (?, ?, ?, ?)", (_iso(), turn_id, what, why)
        )

    def recent_turns(self, hours: float = 24) -> list[dict]:
        since = (_now() - timedelta(hours=hours)).isoformat()
        return self._rows("SELECT * FROM turns WHERE at >= ? ORDER BY id", (since,))

    def tools_of(self, turn_id: int) -> list[dict]:
        return self._rows("SELECT * FROM tool_calls WHERE turn_id = ? ORDER BY id", (turn_id,))

    # ── cards ──────────────────────────────────────────────────────────────

    def card_put(self, device: str, cid: str, title: str | None, snapshot: list[dict] | None) -> None:
        now = _iso()
        row = self.conn.execute("SELECT title FROM cards WHERE device = ? AND id = ?", (device, cid)).fetchone()
        if row is None:
            self._write(
                "INSERT INTO cards (device, id, title, snapshot, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (device, cid, title or cid, json.dumps(snapshot) if snapshot is not None else None, now, now),
            )
            return
        self._write(
            "UPDATE cards SET title = ?, snapshot = COALESCE(?, snapshot), updated_at = ?, closed_at = NULL,"
            " created_at = CASE WHEN closed_at IS NULL THEN created_at ELSE ? END"
            " WHERE device = ? AND id = ?",
            (
                title or row["title"],
                json.dumps(snapshot) if snapshot is not None else None,
                now,
                now,
                device,
                cid,
            ),
        )

    def card_thread(self, device: str, cid: str, q: str, a: str, keep: int = 6) -> list[dict]:
        row = self.conn.execute("SELECT thread FROM cards WHERE device = ? AND id = ?", (device, cid)).fetchone()
        thread = json.loads(row["thread"]) if row else []
        thread = [*thread, {"q": q, "a": a}][-keep:]
        self._write(
            "UPDATE cards SET thread = ?, updated_at = ? WHERE device = ? AND id = ?",
            (json.dumps(thread, ensure_ascii=False), _iso(), device, cid),
        )
        return thread

    def card_close(self, device: str, cid: str) -> None:
        self._write(
            "UPDATE cards SET closed_at = ? WHERE device = ? AND id = ? AND closed_at IS NULL", (_iso(), device, cid)
        )

    def cards_open(self, device: str) -> list[dict]:
        rows = self._rows(
            "SELECT * FROM cards WHERE device = ? AND closed_at IS NULL ORDER BY created_at, rowid", (device,)
        )
        for r in rows:
            r["snapshot"] = json.loads(r["snapshot"]) if r["snapshot"] else None
            r["thread"] = json.loads(r["thread"] or "[]")
        return rows

    # ── agenda ─────────────────────────────────────────────────────────────

    def agenda_add(
        self, kind: str, due_at: str, label: str, repeat_days: str | None = None, on_device: bool = False
    ) -> int:
        return self._write(
            "INSERT INTO agenda (kind, due_at, label, repeat_days, on_device, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (kind, due_at, label, repeat_days, int(on_device), _iso()),
        )

    def agenda_live(self) -> list[dict]:
        return self._rows("SELECT * FROM agenda WHERE ended_at IS NULL ORDER BY due_at")

    def agenda_get(self, item_id: int) -> dict | None:
        rows = self._rows("SELECT * FROM agenda WHERE id = ?", (item_id,))
        return rows[0] if rows else None

    def agenda_due(self, local_now: str) -> list[dict]:
        return self._rows(
            "SELECT * FROM agenda WHERE ended_at IS NULL AND rang_at IS NULL AND due_at <= ? ORDER BY due_at",
            (local_now,),
        )

    def agenda_rang(self, item_id: int) -> None:
        self._write("UPDATE agenda SET rang_at = ? WHERE id = ?", (_iso(), item_id))

    def agenda_move(self, item_id: int, due_at: str) -> None:
        self._write("UPDATE agenda SET due_at = ?, rang_at = NULL WHERE id = ?", (due_at, item_id))

    def agenda_end(self, item_id: int, how: str) -> None:
        self._write(
            "UPDATE agenda SET ended_at = ?, ended_how = ? WHERE id = ? AND ended_at IS NULL", (_iso(), how, item_id)
        )

    # ── lists ──────────────────────────────────────────────────────────────

    def list_items(self, name: str) -> list[dict]:
        return self._rows(
            "SELECT * FROM list_items WHERE list_name = ? AND removed_at IS NULL ORDER BY done, id", (name,)
        )

    def list_add(self, name: str, item: str) -> bool:
        for row in self.list_items(name):
            if row["item"].lower() == item.lower():
                if row["done"]:
                    self._write("UPDATE list_items SET done = 0 WHERE id = ?", (row["id"],))
                    return True
                return False
        self._write("INSERT INTO list_items (list_name, item, added_at) VALUES (?, ?, ?)", (name, item, _iso()))
        return True

    def _list_find(self, name: str, item: str) -> dict | None:
        wanted = item.lower().strip()
        rows = self.list_items(name)
        for row in rows:
            if row["item"].lower() == wanted:
                return row
        for row in rows:
            if wanted in row["item"].lower() or row["item"].lower() in wanted:
                return row
        return None

    def list_remove(self, name: str, item: str) -> str | None:
        row = self._list_find(name, item)
        if row is None:
            return None
        self._write("UPDATE list_items SET removed_at = ? WHERE id = ?", (_iso(), row["id"]))
        return row["item"]

    def list_check(self, name: str, item: str, done: bool = True) -> str | None:
        row = self._list_find(name, item)
        if row is None:
            return None
        self._write("UPDATE list_items SET done = ? WHERE id = ?", (int(done), row["id"]))
        return row["item"]

    def list_clear(self, name: str, only_done: bool = False) -> int:
        rows = [r for r in self.list_items(name) if r["done"] or not only_done]
        for r in rows:
            self._write("UPDATE list_items SET removed_at = ? WHERE id = ?", (_iso(), r["id"]))
        return len(rows)

    def list_names(self) -> list[str]:
        return [
            r["list_name"] for r in self._rows("SELECT DISTINCT list_name FROM list_items WHERE removed_at IS NULL")
        ]

    # ── memories ───────────────────────────────────────────────────────────

    def memories(self) -> list[dict]:
        return self._rows("SELECT * FROM memories WHERE ended_at IS NULL ORDER BY about, id")

    def memory_add(self, fact: str, about: str = "") -> int:
        fact, about = fact.strip(), about.strip()
        for row in self.memories():
            if row["fact"].lower() == fact.lower() and row["about"].lower() == about.lower():
                return int(row["id"])
        return self._write("INSERT INTO memories (about, fact, created_at) VALUES (?, ?, ?)", (about, fact, _iso()))

    def memory_end(self, memory_id: int, why: str) -> dict | None:
        rows = self._rows("SELECT * FROM memories WHERE id = ? AND ended_at IS NULL", (memory_id,))
        if not rows:
            return None
        self._write("UPDATE memories SET ended_at = ?, ended_why = ? WHERE id = ?", (_iso(), why, memory_id))
        return rows[0]

    # ── trust ──────────────────────────────────────────────────────────────

    def trusted(self, tool: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM trust WHERE tool = ? AND revoked_at IS NULL", (tool,)).fetchone()
        return row is not None

    def grant(self, tool: str) -> None:
        self._write(
            "INSERT INTO trust (tool, granted_at) VALUES (?, ?)"
            " ON CONFLICT(tool) DO UPDATE SET granted_at = excluded.granted_at, revoked_at = NULL",
            (tool, _iso()),
        )

    def revoke(self, tool: str) -> None:
        self._write("UPDATE trust SET revoked_at = ? WHERE tool = ? AND revoked_at IS NULL", (_iso(), tool))

    def trust_list(self) -> list[dict]:
        return self._rows("SELECT * FROM trust ORDER BY granted_at DESC")
