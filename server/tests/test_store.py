from datetime import UTC, datetime, timedelta
from pathlib import Path

from pino.store import Store


def test_after_thirty_days_audio_goes_text_stays(settings):
    store = Store(settings.db_path, settings.audio_dir)
    rid = store.save_recording(b"\x00\x00" * 16000, "tablet")
    store.set_transcript(rid, "ciao", "finto")
    row = store.conn.execute("SELECT * FROM recordings WHERE id = ?", (rid,)).fetchone()
    assert Path(row["path"]).exists() and row["seconds"] == 1.0

    assert store.purge(30) == 0
    later = datetime.now(UTC) + timedelta(days=31)
    assert store.purge(30, now=later) == 1
    row = store.conn.execute("SELECT * FROM recordings WHERE id = ?", (rid,)).fetchone()
    assert row["path"] is None and row["purged_at"] and row["transcript"] == "ciao"
