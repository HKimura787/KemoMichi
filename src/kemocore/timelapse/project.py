"""An open Timelapse2 data file (.ddb): read, query and edit it without breaking compatibility."""

from __future__ import annotations

import json
import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from . import constants as C
from . import schema as S
from .template import Control, ValueError_, control_from_row, default_for_new_control, normalize_value
from .versions import compare_versions


class ProjectError(Exception):
    """A file that cannot be opened. `key` is a message key for the UI."""

    def __init__(self, key: str, **params):
        super().__init__(key)
        self.key = key
        self.params = params


@dataclass
class Change:
    file_id: int
    data_label: str
    old: str
    new: str


@dataclass
class Batch:
    changes: list[Change] = field(default_factory=list)
    description: str = ""


BACKUP_INTERVAL = timedelta(minutes=30)
BACKUPS_KEPT = 8
BACKUP_MAX_AGE = timedelta(days=14)


def backup_file(path: Path) -> Path:
    """Copy `path` into Backups/ with Timelapse's naming, then apply its retention rule (spec §7)."""
    folder = path.parent / C.BACKUP_FOLDER
    folder.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d.%H-%M-%S")
    target = folder / f"{path.stem}.{stamp}{path.suffix}"
    shutil.copy2(path, target)
    backups = sorted(folder.glob(f"{path.stem}.*{path.suffix}"), key=lambda p: p.stat().st_mtime, reverse=True)
    backups = [b for b in backups if ".Checkpoint-" not in b.name]
    cutoff = time.time() - BACKUP_MAX_AGE.total_seconds()
    for old in backups[BACKUPS_KEPT:]:
        if old.stat().st_mtime < cutoff:
            old.unlink(missing_ok=True)
    return target


def latest_backup_time(path: Path) -> datetime | None:
    folder = path.parent / C.BACKUP_FOLDER
    if not folder.is_dir():
        return None
    times = [b.stat().st_mtime for b in folder.glob(f"{path.stem}.*{path.suffix}")]
    return datetime.fromtimestamp(max(times)) if times else None


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({S.q(table)})")]


class TimelapseProject:
    def __init__(self, ddb_path: str | Path, read_only: bool = False):
        self.path = Path(ddb_path).resolve()
        if not self.path.is_file():
            raise ProjectError("error.notFound", path=str(self.path))
        self.root = self.path.parent
        self.lock = threading.RLock()
        mode = "ro" if read_only else "rw"
        self.conn = sqlite3.connect(S.sqlite_uri(self.path, mode), uri=True, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.read_only = read_only
        self.read_only_reason = "readOnly.requested" if read_only else ""
        self.undo_stack: list[Batch] = []
        self.redo_stack: list[Batch] = []
        self._backed_up_this_session = False
        self._validate()
        self.reload_template()

    # ---- opening ---------------------------------------------------------------------------

    def _validate(self) -> None:
        conn = self.conn
        try:
            check = conn.execute("PRAGMA quick_check").fetchone()[0]
        except sqlite3.DatabaseError as exc:
            raise ProjectError("error.notSqlite") from exc
        if check != "ok":
            raise ProjectError("error.corrupt", detail=check)
        if not _table_exists(conn, C.DATA_TABLE) or not _table_exists(conn, C.TEMPLATE_TABLE):
            raise ProjectError("error.notDdb")
        if "UtcOffset" in _columns(conn, C.DATA_TABLE):
            raise ProjectError("error.tooOld")
        if not _table_exists(conn, C.IMAGE_SET_TABLE):
            raise ProjectError("error.notDdb")
        cols = _columns(conn, C.IMAGE_SET_TABLE)
        if "VersionCompatabily" not in cols:
            raise ProjectError("error.tooOld")
        row = self.image_set()
        version = row.get("VersionCompatabily") or ""
        if compare_versions(version, C.MINIMUM_VERSION) < 0:
            raise ProjectError("error.tooOld")
        backwards = row.get("BackwardsCompatibility") or ""
        if backwards and compare_versions(backwards, C.NEWEST_UNDERSTOOD_BACKWARDS) > 0:
            self.read_only = True
            self.read_only_reason = "readOnly.newerFile"
        types = {r[0] for r in conn.execute(f"SELECT Type FROM {C.TEMPLATE_TABLE}")}
        unknown = types - set(C.ALL_TYPES) - {None}
        if unknown:
            raise ProjectError("error.unknownType", types=", ".join(sorted(unknown)))

    def reload_template(self) -> None:
        rows = [dict(r) for r in self.conn.execute(f"SELECT * FROM {C.TEMPLATE_TABLE} ORDER BY ControlOrder, Id")]
        self.controls: list[Control] = [control_from_row(r) for r in rows]
        self.by_label = {c.data_label: c for c in self.controls}
        self.columns = _columns(self.conn, C.DATA_TABLE)
        # Template rows whose column is missing would make every query fail; skip them.
        self.controls = [c for c in self.controls if c.data_label in self.columns]

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    def image_set(self) -> dict:
        row = self.conn.execute(f"SELECT * FROM {C.IMAGE_SET_TABLE} ORDER BY Id LIMIT 1").fetchone()
        return dict(row) if row else {}

    def info(self) -> dict:
        image_set = self.image_set()
        return {
            "path": str(self.path),
            "root": str(self.root),
            "name": self.path.name,
            "readOnly": self.read_only,
            "readOnlyReason": self.read_only_reason,
            "version": image_set.get("VersionCompatabily"),
            "backwardsCompatibility": image_set.get("BackwardsCompatibility"),
            "standard": image_set.get("Standard") or "",
            "controls": [c.to_dict() for c in self.controls],
            "total": self.count({}),
            "hasRecognitions": _table_exists(self.conn, C.DETECTIONS),
        }

    # ---- reading ---------------------------------------------------------------------------

    def _where(self, flt: dict) -> tuple[str, list]:
        clauses, params = [], []
        folder = flt.get("folder")
        if folder:
            folder = folder.strip("\\")
            clauses.append("(RelativePath = ? OR RelativePath LIKE ? ESCAPE '!')")
            escaped = folder.replace("!", "!!").replace("%", "!%").replace("_", "!_")
            params += [folder, escaped + "\\%"]
        if "deleted" in flt and flt["deleted"] is not None:
            clauses.append("lower(DeleteFlag) = ?")
            params.append(C.TRUE if flt["deleted"] else C.FALSE)
        for cond in flt.get("equals") or []:
            label = cond.get("label")
            if label in self.by_label:
                clauses.append(f"{S.q(label)} = ?")
                params.append(str(cond.get("value", "")))
        any_flags = [l for l in flt.get("anyTrue") or [] if l in self.by_label]
        if any_flags:
            clauses.append("(" + " OR ".join(f"lower({S.q(l)}) = 'true'" for l in any_flags) + ")")
        none_flags = [l for l in flt.get("allFalse") or [] if l in self.by_label]
        for label in none_flags:
            clauses.append(f"lower(coalesce({S.q(label)}, '')) <> 'true'")
        text = (flt.get("text") or "").strip()
        if text:
            text_cols = [c.data_label for c in self.controls
                         if c.type in (C.FILE, C.RELATIVE_PATH, C.NOTE, C.MULTI_LINE, C.FIXED_CHOICE,
                                       C.MULTI_CHOICE, C.ALPHA_NUMERIC)]
            if text_cols:
                clauses.append("(" + " OR ".join(f"{S.q(c)} LIKE ?" for c in text_cols) + ")")
                params += [f"%{text}%"] * len(text_cols)
        detection = flt.get("detection")
        if detection and _table_exists(self.conn, C.DETECTIONS):
            min_conf = float(detection.get("minConf", 0.0))
            category = detection.get("category")
            if category == "none":
                clauses.append(
                    f"Id NOT IN (SELECT Id FROM {C.DETECTIONS} WHERE category <> '0' AND conf >= ?)")
                params.append(min_conf)
            elif category:
                sub = f"SELECT Id FROM {C.DETECTIONS} WHERE conf >= ?"
                sub_params: list = [min_conf]
                if category != "any":
                    sub += " AND category = ?"
                    sub_params.append(str(category))
                else:
                    sub += " AND category <> '0'"
                clauses.append(f"Id IN ({sub})")
                params += sub_params
        if flt.get("excludeIds"):
            excluded = [int(i) for i in flt["excludeIds"]]
            clauses.append(f"Id NOT IN ({','.join('?' for _ in excluded)})")
            params += excluded
        if flt.get("ids"):
            ids = [int(i) for i in flt["ids"]]
            clauses.append(f"Id IN ({','.join('?' for _ in ids)})")
            params += ids
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    ORDER = " ORDER BY RelativePath, DateTime, File, Id"

    def count(self, flt: dict) -> int:
        where, params = self._where(flt)
        with self.lock:
            return self.conn.execute(f"SELECT COUNT(*) FROM {C.DATA_TABLE}{where}", params).fetchone()[0]

    def files(self, flt: dict, offset: int = 0, limit: int = 200) -> list[dict]:
        where, params = self._where(flt)
        with self.lock:
            rows = self.conn.execute(
                f"SELECT * FROM {C.DATA_TABLE}{where}{self.ORDER} LIMIT ? OFFSET ?",
                params + [limit, offset]).fetchall()
        return [self._row(r) for r in rows]

    def ids(self, flt: dict) -> list[int]:
        where, params = self._where(flt)
        with self.lock:
            return [r[0] for r in self.conn.execute(f"SELECT Id FROM {C.DATA_TABLE}{where}{self.ORDER}", params)]

    def position(self, flt: dict, file_id: int) -> int:
        """Index of a file within the filtered, sorted list (-1 if absent)."""
        ids = self.ids(flt)
        try:
            return ids.index(file_id)
        except ValueError:
            return -1

    def file(self, file_id: int) -> dict | None:
        with self.lock:
            row = self.conn.execute(f"SELECT * FROM {C.DATA_TABLE} WHERE Id = ?", (file_id,)).fetchone()
        return self._row(row) if row else None

    def _row(self, row: sqlite3.Row) -> dict:
        values = {c.data_label: ("" if row[c.data_label] is None else str(row[c.data_label])) for c in self.controls}
        return {"id": row["Id"], "values": values}

    def media_path(self, row: dict) -> Path:
        rel = row["values"].get(C.RELATIVE_PATH, "")
        name = row["values"].get(C.FILE, "")
        parts = [p for p in rel.split("\\") if p]
        return self.root.joinpath(*parts, name)

    def folders(self) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                f"SELECT RelativePath, COUNT(*) FROM {C.DATA_TABLE} GROUP BY RelativePath ORDER BY RelativePath"
            ).fetchall()
        return [{"path": r[0] or "", "count": r[1]} for r in rows]

    def markers(self, file_id: int) -> dict[str, list[list[float]]]:
        if not _table_exists(self.conn, C.MARKERS_TABLE):
            return {}
        with self.lock:
            row = self.conn.execute(f"SELECT * FROM {C.MARKERS_TABLE} WHERE Id = ?", (file_id,)).fetchone()
        if row is None:
            return {}
        result = {}
        for key in row.keys():
            if key == "Id":
                continue
            result[key] = parse_marker_points(row[key])
        return result

    # ---- recognitions ----------------------------------------------------------------------

    def detection_categories(self) -> dict:
        if not _table_exists(self.conn, C.DETECTION_CATEGORIES):
            return {"detection": {}, "classification": {}}
        with self.lock:
            det = {str(r[0]): r[1] for r in self.conn.execute(f"SELECT category, label FROM {C.DETECTION_CATEGORIES}")}
            cls = {}
            if _table_exists(self.conn, C.CLASSIFICATION_CATEGORIES):
                cls = {str(r[0]): r[1] for r in self.conn.execute(
                    f"SELECT classification, label FROM {C.CLASSIFICATION_CATEGORIES}")}
        return {"detection": det, "classification": cls}

    def detections(self, file_id: int) -> list[dict]:
        if not _table_exists(self.conn, C.DETECTIONS):
            return []
        video = _table_exists(self.conn, C.DETECTIONS_VIDEO)
        sql = (f"SELECT d.detectionID, d.category, d.conf, d.bbox, d.classification, d.classification_conf"
               + (", v.frame_number, v.frame_rate" if video else "")
               + f" FROM {C.DETECTIONS} d"
               + (f" LEFT JOIN {C.DETECTIONS_VIDEO} v USING (detectionID)" if video else "")
               + " WHERE d.Id = ? ORDER BY d.detectionID")
        with self.lock:
            rows = self.conn.execute(sql, (file_id,)).fetchall()
        out = []
        for r in rows:
            bbox = parse_bbox(r["bbox"])
            if bbox is None:
                continue
            out.append({
                "id": r["detectionID"], "category": str(r["category"]), "conf": r["conf"], "bbox": bbox,
                "classification": None if r["classification"] is None else str(r["classification"]),
                "classificationConf": r["classification_conf"],
                "frame": (r["frame_number"] if video and r["frame_number"] is not None else None),
                "frameRate": (r["frame_rate"] if video else None),
            })
        return out

    # ---- writing ---------------------------------------------------------------------------

    def _ensure_writable(self) -> None:
        if self.read_only:
            raise ProjectError(self.read_only_reason or "readOnly.requested")

    def _backup_if_needed(self) -> None:
        last = latest_backup_time(self.path)
        if not self._backed_up_this_session or last is None or datetime.now() - last > BACKUP_INTERVAL:
            backup_file(self.path)
            self._backed_up_this_session = True

    def update(self, file_ids: list[int], values: dict[str, object], description: str = "",
               record_undo: bool = True) -> Batch:
        """Set the same values on every file. Validates every value first; all or nothing.

        `record_undo=False` is for values derived from other records (events), which are rewritten
        from their source whenever it changes, so undoing them on their own would only desync them.
        """
        self._ensure_writable()
        normalized: dict[str, str] = {}
        for label, value in values.items():
            control = self.by_label.get(label)
            if control is None:
                raise ProjectError("error.unknownField", field=label)
            if control.type in (C.FILE, C.RELATIVE_PATH):
                raise ProjectError("error.readOnlyField", field=label)
            normalized[label] = normalize_value(control, value)
        if not normalized or not file_ids:
            return Batch(description=description)
        batch = Batch(description=description)
        with self.lock:
            self._backup_if_needed()
            labels = list(normalized)
            for chunk_start in range(0, len(file_ids), 500):
                chunk = file_ids[chunk_start:chunk_start + 500]
                rows = self.conn.execute(
                    f"SELECT Id, {', '.join(S.q(l) for l in labels)} FROM {C.DATA_TABLE} "
                    f"WHERE Id IN ({','.join('?' for _ in chunk)})", chunk).fetchall()
                for row in rows:
                    for label in labels:
                        old = "" if row[label] is None else str(row[label])
                        if old != normalized[label]:
                            batch.changes.append(Change(row["Id"], label, old, normalized[label]))
            self._apply(batch.changes, forward=True)
        if batch.changes and record_undo:
            self.undo_stack.append(batch)
            self.redo_stack.clear()
        return batch

    def same_file_ids(self, file_id: int) -> list[int]:
        """Every DataTable row for the same file (Timelapse allows duplicates), oldest first."""
        with self.lock:
            row = self.conn.execute(f"SELECT File, RelativePath FROM {C.DATA_TABLE} WHERE Id = ?",
                                    (file_id,)).fetchone()
            if row is None:
                return []
            return [r[0] for r in self.conn.execute(
                f"SELECT Id FROM {C.DATA_TABLE} WHERE File = ? AND RelativePath = ? ORDER BY Id",
                (row["File"], row["RelativePath"]))]

    def duplicate_row(self, source_id: int) -> int:
        """Add a copy of a row, like Timelapse's duplicate record. Returns the new Id."""
        self._ensure_writable()
        labels = [c.data_label for c in self.controls]
        cols = ", ".join(S.q(l) for l in labels)
        with self.lock:
            self._backup_if_needed()
            with self.conn:
                cur = self.conn.execute(
                    f"INSERT INTO {C.DATA_TABLE} ({cols}) SELECT {cols} FROM {C.DATA_TABLE} WHERE Id = ?",
                    (source_id,))
            return cur.lastrowid

    def delete_rows(self, ids: list[int]) -> None:
        """Remove rows (and their markers) without touching the media files."""
        self._ensure_writable()
        if not ids:
            return
        marks = ",".join("?" for _ in ids)
        with self.lock:
            self._backup_if_needed()
            with self.conn:
                if _table_exists(self.conn, C.MARKERS_TABLE):
                    self.conn.execute(f"DELETE FROM {C.MARKERS_TABLE} WHERE Id IN ({marks})", ids)
                self.conn.execute(f"DELETE FROM {C.DATA_TABLE} WHERE Id IN ({marks})", ids)

    def _apply(self, changes: list[Change], forward: bool) -> None:
        with self.conn:
            for ch in changes:
                self.conn.execute(
                    f"UPDATE {C.DATA_TABLE} SET {S.q(ch.data_label)} = ? WHERE Id = ?",
                    (ch.new if forward else ch.old, ch.file_id))

    def undo(self) -> Batch | None:
        self._ensure_writable()
        if not self.undo_stack:
            return None
        batch = self.undo_stack.pop()
        with self.lock:
            self._apply(batch.changes, forward=False)
        self.redo_stack.append(batch)
        return batch

    def redo(self) -> Batch | None:
        self._ensure_writable()
        if not self.redo_stack:
            return None
        batch = self.redo_stack.pop()
        with self.lock:
            self._apply(batch.changes, forward=True)
        self.undo_stack.append(batch)
        return batch

    def set_markers(self, file_id: int, data_label: str, points: list[list[float]]) -> None:
        """Store counter marker points (normalized 0-1) the way Timelapse does (spec §2.4)."""
        self._ensure_writable()
        control = self.by_label.get(data_label)
        if control is None or control.type != C.COUNTER:
            raise ProjectError("error.unknownField", field=data_label)
        with self.lock:
            self._backup_if_needed()
            cols = _columns(self.conn, C.MARKERS_TABLE) if _table_exists(self.conn, C.MARKERS_TABLE) else []
            if data_label not in cols:
                raise ProjectError("error.unknownField", field=data_label)
            text = format_marker_points(points)
            with self.conn:
                exists = self.conn.execute(f"SELECT 1 FROM {C.MARKERS_TABLE} WHERE Id = ?", (file_id,)).fetchone()
                if not exists:
                    counter_cols = [c for c in cols if c != "Id"]
                    self.conn.execute(
                        f"INSERT INTO {C.MARKERS_TABLE} (Id, {', '.join(S.q(c) for c in counter_cols)}) "
                        f"VALUES (?, {', '.join(repr('[]') for _ in counter_cols)})", (file_id,))
                self.conn.execute(f"UPDATE {C.MARKERS_TABLE} SET {S.q(data_label)} = ? WHERE Id = ?",
                                  (text, file_id))

    def duplicate(self, file_id: int) -> int:
        """Duplicate a record for the same media file (matching Timelapse's duplicate record feature)."""
        self._ensure_writable()
        with self.lock:
            self._backup_if_needed()
            row = self.conn.execute(f"SELECT * FROM {C.DATA_TABLE} WHERE Id = ?", (file_id,)).fetchone()
            if row is None:
                raise ProjectError("error.fileNotFound")

            cols = [c.data_label for c in self.controls]
            vals = []
            for c in self.controls:
                if c.data_label == C.DELETE_FLAG:
                    vals.append(C.FALSE)
                else:
                    v = row[c.data_label]
                    vals.append("" if v is None else str(v))

            with self.conn:
                sql = (f"INSERT INTO {C.DATA_TABLE} ({', '.join(S.q(c) for c in cols)}) "
                       f"VALUES ({', '.join('?' for _ in cols)})")
                cur = self.conn.execute(sql, vals)
                new_id = cur.lastrowid

                if _table_exists(self.conn, C.DETECTIONS):
                    det_rows = self.conn.execute(
                        f"SELECT detectionID, category, conf, bbox, classification, classification_conf "
                        f"FROM {C.DETECTIONS} WHERE Id = ?",
                        (file_id,)
                    ).fetchall()
                    has_video = _table_exists(self.conn, C.DETECTIONS_VIDEO)
                    for dr in det_rows:
                        d_cur = self.conn.execute(
                            f"INSERT INTO {C.DETECTIONS} (category, conf, bbox, classification, "
                            f"classification_conf, Id) VALUES (?, ?, ?, ?, ?, ?)",
                            (dr["category"], dr["conf"], dr["bbox"], dr["classification"],
                             dr["classification_conf"], new_id)
                        )
                        if has_video:
                            new_det_id = d_cur.lastrowid
                            v_rows = self.conn.execute(
                                f"SELECT frame_number, frame_rate FROM {C.DETECTIONS_VIDEO} WHERE detectionID = ?",
                                (dr["detectionID"],)
                            ).fetchall()
                            for vr in v_rows:
                                self.conn.execute(
                                    f"INSERT INTO {C.DETECTIONS_VIDEO} (frame_number, frame_rate, detectionID) "
                                    f"VALUES (?, ?, ?)",
                                    (vr["frame_number"], vr["frame_rate"], new_det_id)
                                )
            return new_id

    def file_records_info(self, file_id: int) -> dict:
        """Count how many records share the same RelativePath + File, and this file's 1-based index."""
        row = self.file(file_id)
        if row is None:
            return {"index": 1, "total": 1}
        rel = row["values"].get(C.RELATIVE_PATH, "")
        file_name = row["values"].get(C.FILE, "")
        with self.lock:
            rows = self.conn.execute(
                f"SELECT Id FROM {C.DATA_TABLE} WHERE RelativePath = ? AND File = ? ORDER BY Id",
                (rel, file_name)
            ).fetchall()
        ids = [r[0] for r in rows]
        total = len(ids)
        try:
            idx = ids.index(file_id) + 1
        except ValueError:
            idx = 1
        return {"index": idx, "total": total}

    def add_controls(self, new_controls: list[dict], template_path: Path | None = None) -> list[Control]:
        """Append user controls to the .ddb (and its .tdb) as a Timelapse template sync would (spec §6).

        Each item: {"type": ..., "label": ..., "dataLabel": ...}.
        """
        self._ensure_writable()
        year = datetime.now().year
        with self.lock:
            self._backup_if_needed()
            targets = [(self.conn, True)]
            tconn = None
            if template_path is not None:
                backup_file(template_path)
                tconn = sqlite3.connect(template_path)
                targets.append((tconn, False))
            added: list[Control] = []
            try:
                for conn, is_data in targets:
                    count = conn.execute(f"SELECT COUNT(*) FROM {C.TEMPLATE_TABLE}").fetchone()[0]
                    taken = {r[0] for r in conn.execute(f"SELECT DataLabel FROM {C.TEMPLATE_TABLE}")}
                    with conn:
                        for item in new_controls:
                            ctype = item["type"]
                            if ctype not in C.USER_TYPES:
                                raise ProjectError("error.unknownType", types=ctype)
                            label = item["dataLabel"]
                            if label in taken:
                                raise ProjectError("error.duplicateField", field=label)
                            count += 1
                            prefix, _default, width, copyable = C.NEW_CONTROL_DEFAULTS[ctype]
                            control = Control(
                                id=0, control_order=count, spreadsheet_order=count, type=ctype,
                                default_value=default_for_new_control(ctype, year), label=item.get("label") or label,
                                data_label=label, tooltip=item.get("tooltip", ""), visible=True, list_raw="",
                                export_to_csv=True, width=width, copyable=copyable,
                            )
                            conn.execute(S.INSERT_TEMPLATE_ROW, S.template_row_values(control))
                            taken.add(label)
                            if is_data:
                                conn.execute(f"ALTER TABLE {C.DATA_TABLE} ADD COLUMN {S.data_column_sql(control)}")
                                if ctype == C.COUNTER and _table_exists(conn, C.MARKERS_TABLE):
                                    conn.execute(f"ALTER TABLE {C.MARKERS_TABLE} ADD COLUMN "
                                                 f"{S.q(label)} TEXT DEFAULT '[]'")
                                if ctype in C.NUMBER_TYPES:
                                    # The column default is '' for numbers; rows get the control default.
                                    conn.execute(f"UPDATE {C.DATA_TABLE} SET {S.q(label)} = ?",
                                                 (control.default_value,))
                                added.append(control)
            finally:
                if tconn is not None:
                    tconn.close()
            self.reload_template()
        return added

    def find_template(self) -> Path | None:
        """The .tdb next to this .ddb whose data labels match, if exactly one does."""
        mine = {c.data_label for c in self.controls}
        matches = []
        for candidate in self.root.glob("*.tdb"):
            try:
                conn = sqlite3.connect(S.sqlite_uri(candidate), uri=True)
                labels = {r[0] for r in conn.execute(f"SELECT DataLabel FROM {C.TEMPLATE_TABLE}")}
                conn.close()
            except sqlite3.DatabaseError:
                continue
            if labels == mine:
                matches.append(candidate)
        return matches[0] if len(matches) == 1 else None


def parse_bbox(raw) -> list[float] | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        parts = [float(p) for p in str(raw).split(",")]
    except ValueError:
        return None
    return parts if len(parts) == 4 else None


def parse_marker_points(raw) -> list[list[float]]:
    """Read MarkersTable JSON; each point may be a "x,y" string or an object (spec §2.4, unverified)."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    points = []
    for item in data if isinstance(data, list) else []:
        try:
            if isinstance(item, str):
                x, y = (float(v) for v in item.split(","))
            elif isinstance(item, dict):
                x, y = float(item.get("X", item.get("x"))), float(item.get("Y", item.get("y")))
            else:
                continue
        except (TypeError, ValueError):
            break
        points.append([x, y])
    return points


def format_marker_points(points: list[list[float]]) -> str:
    def num(v: float) -> str:
        text = f"{round(float(v), 4):.4f}".rstrip("0").rstrip(".")
        return text or "0"

    return json.dumps([f"{num(x)},{num(y)}" for x, y in points], separators=(",", ":"))
