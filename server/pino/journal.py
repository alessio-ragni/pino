"""`python -m pino.journal`: what Pino did, read from its database.

    python -m pino.journal --hours 6        # questions, timings, tools, discards, missing tools
    python -m pino.journal --db /path/pino.db

It opens the database read-only: it never changes anything.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pino.config import Settings


def _ms(v: int | None) -> str:
    return "—" if v is None else f"{v / 1000:.1f}s"


def report(db: Path, hours: float) -> str:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    out = [f"Last {hours:g} hours (times in UTC)", ""]
    turns = conn.execute("SELECT * FROM turns WHERE at >= ? ORDER BY id", (since,)).fetchall()
    for t in turns:
        out.append(
            f"#{t['id']} {t['at'][11:19]} [{t['why']}] «{(t['asked'] or '')[:80]}»"
            f"  → card {t['card'] or '—'}, {t['outcome'] or '?'}"
        )
        out.append(
            f"    heard {_ms(t['ms_transcribe'])} · first word {_ms(t['ms_first_text'])}"
            f" · first sound {_ms(t['ms_first_audio'])} · total {_ms(t['ms_total'])}"
            f" · model calls {t['num_turns'] or '—'} · cached tokens {t['cache_read_tokens'] or 0}"
        )
        if t["answered"]:
            out.append(f"    said: {t['answered'][:160]}")
        if t["error"]:
            out.append(f"    error: {t['error'][:200]}")
        for c in conn.execute("SELECT * FROM tool_calls WHERE turn_id = ? ORDER BY id", (t["id"],)):
            flag = "ok" if c["ok"] else f"FAILED {c['error'] or ''}"[:120]
            asked = f" (confirm: {c['confirmed']})" if c["confirmed"] else ""
            out.append(f"    tool {c['tool']} {_ms(c['ms'])} {flag}{asked}")
    if not turns:
        out.append("No questions.")
    events = conn.execute("SELECT kind, detail FROM events WHERE at >= ?", (since,)).fetchall()
    counts = Counter(f"{e['kind']}:{e['detail']}" if e["kind"] == "ignored" else e["kind"] for e in events)
    if counts:
        out += ["", "Events: " + ", ".join(f"{k} ×{n}" for k, n in counts.most_common())]
    missing = conn.execute("SELECT at, what, why FROM missing_tools WHERE at >= ?", (since,)).fetchall()
    if missing:
        out += ["", "Missing tools:"] + [f"  {m['at'][:16]} {m['what']} {m['why'] or ''}" for m in missing]
    errors = [json.loads(e["detail"]) for e in events if e["kind"] == "render_error" and e["detail"]]
    if errors:
        out += ["", "Cards that failed to draw:"] + [f"  {e.get('surfaceId')}: {e.get('message')}" for e in errors]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="What Pino did.")
    parser.add_argument("--hours", type=float, default=24)
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()
    print(report(args.db or Settings.from_env().db_path, args.hours))


if __name__ == "__main__":
    main()
