"""KemoMichi's own data, kept next to the .ddb so the Timelapse2 file stays untouched (plan §3 rule 3).

The sidecar is `<ddb name>.kemomichi` (SQLite) beside the .ddb. It holds project settings (species
palette, column mapping), per-folder settings (guide shapes, colour presets) and REST events: one
animal's stay in the focal area, from entry to exit, possibly across several videos (plan §6.3).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from .timelapse.schema import sqlite_uri

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS folder_settings (
    folder TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY (folder, key));
CREATE TABLE IF NOT EXISTS intervals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,              -- 'video' (frames of one file) or 'sequence' (several still images)
    file_id INTEGER NOT NULL,        -- the video, or the first image of a sequence
    start_frame INTEGER, end_frame INTEGER,
    start_file_id INTEGER, end_file_id INTEGER,
    start_seconds TEXT, end_seconds TEXT, duration_seconds TEXT,
    individual TEXT NOT NULL DEFAULT '', species TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_intervals_file ON intervals (file_id);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    species TEXT NOT NULL DEFAULT '',          -- DataLabel of the species Flag
    individual TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    start_file_id INTEGER NOT NULL,            -- first DataTable row of the file where the entry is
    start_frame INTEGER,                       -- NULL for a still image
    start_inside INTEGER NOT NULL DEFAULT 0,   -- 1: already inside when that file began
    end_file_id INTEGER,                       -- NULL while the event is open
    end_frame INTEGER,
    end_inside INTEGER NOT NULL DEFAULT 0,     -- 1: still inside when end_file_id ended (never seen leaving)
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_events_start ON events (start_file_id);
CREATE INDEX IF NOT EXISTS idx_events_end ON events (end_file_id);
-- DataTable rows KemoMichi duplicated so a file with several events has one row per event.
CREATE TABLE IF NOT EXISTS duplicate_rows (row_id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL);
"""

_EVENT_COLUMNS = ("species", "individual", "note", "start_file_id", "start_frame", "start_inside",
                  "end_file_id", "end_frame", "end_inside")


def sidecar_path(ddb_path: Path) -> Path:
    return Path(ddb_path).with_name(Path(ddb_path).name + ".kemomichi")


class Sidecar:
    def __init__(self, ddb_path: Path, read_only: bool = False):
        self.path = sidecar_path(ddb_path)
        self.lock = threading.RLock()
        self.read_only = read_only
        if read_only:
            # Never create or change files next to a project opened read-only.
            source = sqlite_uri(self.path) if self.path.exists() else "file::memory:"
            self.conn = sqlite3.connect(source, uri=True, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            if not self.path.exists():
                self.conn.executescript(_SCHEMA)
            return
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.conn:
            self.conn.executescript(_SCHEMA)
            self.conn.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', '1')")
            self._migrate()

    def _migrate(self) -> None:
        version = int(self.conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0])
        if version < 2:
            # Version 1 kept S/E intervals inside one file; each becomes a closed event.
            now = datetime.now().isoformat(timespec="seconds")
            for r in self.conn.execute("SELECT * FROM intervals").fetchall():
                start = r["file_id"] if r["kind"] == "video" else r["start_file_id"]
                end = r["file_id"] if r["kind"] == "video" else r["end_file_id"]
                self.conn.execute(
                    "INSERT INTO events (species, individual, note, start_file_id, start_frame, end_file_id, "
                    "end_frame, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (r["species"], r["individual"], r["note"], start, r["start_frame"], end, r["end_frame"],
                     r["created_at"], now))
            restcols = self.conn.execute("SELECT value FROM settings WHERE key = 'restColumns'").fetchone()
            if restcols:
                old = json.loads(restcols[0])
                new = {"entry": old.get("start"), "exit": old.get("end"), "duration": old.get("duration")}
                self.conn.execute("INSERT OR REPLACE INTO settings VALUES ('eventColumns', ?)", (json.dumps(new),))
        self.conn.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'", (str(SCHEMA_VERSION),))

    def close(self) -> None:
        self.conn.close()

    # settings -------------------------------------------------------------------------------

    def get(self, key: str, default=None):
        with self.lock:
            row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key: str, value) -> None:
        with self.lock, self.conn:
            self.conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value, ensure_ascii=False)))

    def all_settings(self) -> dict:
        with self.lock:
            return {r[0]: json.loads(r[1]) for r in self.conn.execute("SELECT key, value FROM settings")}

    def get_folder(self, folder: str, key: str, default=None, inherit: bool = True):
        """A folder setting; with `inherit`, the nearest parent folder's value applies."""
        folder = folder.strip("\\")
        candidates = [folder]
        if inherit:
            parts = folder.split("\\") if folder else []
            candidates = ["\\".join(parts[:i]) for i in range(len(parts), -1, -1)]
        with self.lock:
            for candidate in candidates:
                row = self.conn.execute("SELECT value FROM folder_settings WHERE folder = ? AND key = ?",
                                        (candidate, key)).fetchone()
                if row:
                    return json.loads(row[0])
        return default

    def set_folder(self, folder: str, key: str, value) -> None:
        with self.lock, self.conn:
            if value is None:
                self.conn.execute("DELETE FROM folder_settings WHERE folder = ? AND key = ?", (folder.strip("\\"), key))
            else:
                self.conn.execute("INSERT OR REPLACE INTO folder_settings VALUES (?, ?, ?)",
                                  (folder.strip("\\"), key, json.dumps(value, ensure_ascii=False)))

    # events --------------------------------------------------------------------------------

    def events(self, where: str = "", params: tuple = ()) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(f"SELECT * FROM events {where} ORDER BY id", params).fetchall()
        return [_event(r) for r in rows]

    def event(self, event_id: int) -> dict | None:
        found = self.events("WHERE id = ?", (event_id,))
        return found[0] if found else None

    def events_touching(self, file_ids: list[int]) -> list[dict]:
        """Events that start or end in any of these rows."""
        if not file_ids:
            return []
        marks = ",".join("?" for _ in file_ids)
        return self.events(f"WHERE start_file_id IN ({marks}) OR end_file_id IN ({marks})", tuple(file_ids) * 2)

    def open_events(self) -> list[dict]:
        return self.events("WHERE end_file_id IS NULL")

    def save_event(self, data: dict) -> dict:
        now = datetime.now().isoformat(timespec="seconds")
        values = []
        for c in _EVENT_COLUMNS:
            v = data.get(c)
            if c in ("species", "individual", "note") and v is None:
                v = ""
            if c in ("start_inside", "end_inside"):
                v = 1 if v else 0
            values.append(v)
        with self.lock, self.conn:
            if data.get("id"):
                self.conn.execute(
                    f"UPDATE events SET {', '.join(f'{c} = ?' for c in _EVENT_COLUMNS)}, updated_at = ? WHERE id = ?",
                    values + [now, data["id"]])
                event_id = data["id"]
            else:
                cur = self.conn.execute(
                    f"INSERT INTO events ({', '.join(_EVENT_COLUMNS)}, created_at, updated_at) "
                    f"VALUES ({', '.join('?' for _ in _EVENT_COLUMNS)}, ?, ?)", values + [now, now])
                event_id = cur.lastrowid
        return self.event(event_id)

    def delete_event(self, event_id: int) -> dict | None:
        existing = self.event(event_id)
        with self.lock, self.conn:
            self.conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        return existing

    # duplicated rows -------------------------------------------------------------------------

    def duplicates_of(self, source_id: int) -> list[int]:
        with self.lock:
            return [r[0] for r in self.conn.execute(
                "SELECT row_id FROM duplicate_rows WHERE source_id = ? ORDER BY row_id", (source_id,))]

    def is_duplicate(self, row_id: int) -> bool:
        with self.lock:
            return self.conn.execute("SELECT 1 FROM duplicate_rows WHERE row_id = ?", (row_id,)).fetchone() is not None

    def all_duplicates(self) -> dict[int, int]:
        with self.lock:
            return {r[0]: r[1] for r in self.conn.execute("SELECT row_id, source_id FROM duplicate_rows")}

    def add_duplicate(self, row_id: int, source_id: int) -> None:
        with self.lock, self.conn:
            self.conn.execute("INSERT OR REPLACE INTO duplicate_rows VALUES (?, ?)", (row_id, source_id))

    def remove_duplicates(self, row_ids: list[int]) -> None:
        with self.lock, self.conn:
            self.conn.executemany("DELETE FROM duplicate_rows WHERE row_id = ?", [(r,) for r in row_ids])


def _event(row: sqlite3.Row) -> dict:
    event = dict(row)
    event["start_inside"] = bool(event["start_inside"])
    event["end_inside"] = bool(event["end_inside"])
    event["open"] = event["end_file_id"] is None
    return event
