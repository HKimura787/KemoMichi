"""KemoMichi's own data, kept next to the .ddb so the Timelapse2 file stays untouched (plan §3 rule 3).

The sidecar is `<ddb name>.kemomichi` (SQLite) beside the .ddb. It holds project settings (species
palette, column mapping), per-folder settings (guide shapes, colour presets) and S/E intervals.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from .timelapse.schema import sqlite_uri

SCHEMA_VERSION = 1

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
CREATE TABLE IF NOT EXISTS file_rest (
    file_id INTEGER PRIMARY KEY,
    start_seconds TEXT,
    end_seconds TEXT,
    duration_seconds TEXT,
    interval_count INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL);
"""


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
            self.conn.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))

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

    # intervals ------------------------------------------------------------------------------

    def intervals(self, file_id: int | None = None) -> list[dict]:
        with self.lock:
            if file_id is None:
                rows = self.conn.execute("SELECT * FROM intervals ORDER BY file_id, id").fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT * FROM intervals WHERE file_id = ? OR start_file_id = ? OR end_file_id = ? ORDER BY id",
                    (file_id, file_id, file_id)).fetchall()
        return [dict(r) for r in rows]

    def interval(self, interval_id: int) -> dict | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM intervals WHERE id = ?", (interval_id,)).fetchone()
        return dict(row) if row else None

    def save_interval(self, data: dict) -> dict:
        now = datetime.now().isoformat(timespec="seconds")
        cols = ["kind", "file_id", "start_frame", "end_frame", "start_file_id", "end_file_id",
                "start_seconds", "end_seconds", "duration_seconds", "individual", "species", "note"]
        values = [data.get(c) if data.get(c) is not None or c not in ("individual", "species", "note") else ""
                  for c in cols]
        with self.lock, self.conn:
            if data.get("id"):
                self.conn.execute(
                    f"UPDATE intervals SET {', '.join(f'{c} = ?' for c in cols)}, updated_at = ? WHERE id = ?",
                    values + [now, data["id"]])
                interval_id = data["id"]
            else:
                cur = self.conn.execute(
                    f"INSERT INTO intervals ({', '.join(cols)}, created_at, updated_at) "
                    f"VALUES ({', '.join('?' for _ in cols)}, ?, ?)", values + [now, now])
                interval_id = cur.lastrowid
        return self.interval(interval_id)

    def delete_interval(self, interval_id: int) -> dict | None:
        existing = self.interval(interval_id)
        with self.lock, self.conn:
            self.conn.execute("DELETE FROM intervals WHERE id = ?", (interval_id,))
        return existing

    # file_rest ------------------------------------------------------------------------------

    def file_rest(self, file_id: int) -> dict | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM file_rest WHERE file_id = ?", (file_id,)).fetchone()
        return dict(row) if row else None

    def save_file_rest(self, file_id: int, start_seconds: str, end_seconds: str,
                       duration_seconds: str, interval_count: int) -> dict | None:
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO file_rest "
                "(file_id, start_seconds, end_seconds, duration_seconds, interval_count, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (file_id, start_seconds, end_seconds, duration_seconds, interval_count, now),
            )
        return self.file_rest(file_id)

    def delete_file_rest(self, file_id: int) -> None:
        with self.lock, self.conn:
            self.conn.execute("DELETE FROM file_rest WHERE file_id = ?", (file_id,))

    def all_file_rest(self) -> dict[int, dict]:
        with self.lock:
            rows = self.conn.execute("SELECT * FROM file_rest").fetchall()
        return {r["file_id"]: dict(r) for r in rows}
