"""Create new .tdb/.ddb files the way Timelapse2 would (spec §1.3, §2)."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from . import constants as C
from . import schema as S
from .template import Control
from ..media_dates import file_datetime


def standard_controls(year: int) -> list[Control]:
    def make(order, sheet, ctype, label, default, width, export):
        return Control(
            id=0, control_order=order, spreadsheet_order=sheet, type=ctype, default_value=default,
            label=label, data_label=ctype, tooltip=C.STANDARD_TOOLTIPS[ctype], visible=True,
            list_raw="", export_to_csv=export, width=width, copyable=False,
        )

    return [
        make(0, 1, C.FILE, "File", "", "100", True),
        make(1, 2, C.RELATIVE_PATH, "RelativePath", "", "100", True),
        make(2, 3, C.DATE_TIME, "DateTime", f"{year}-01-01 12:00:00", "160", True),
        make(3, 4, C.DELETE_FLAG, "Delete?", C.FALSE, "20", False),
    ]


def create_template(path: Path, user_controls: list[Control] | None = None) -> list[Control]:
    """Write a new .tdb. User controls are appended after the four standard ones."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    year = datetime.now().year
    controls = standard_controls(year)
    for control in user_controls or []:
        order = len(controls) + 1
        controls.append(replace(control, control_order=order, spreadsheet_order=order))
    conn = sqlite3.connect(path)
    try:
        with conn:
            conn.execute(S.TEMPLATE_TABLE_SQL)
            conn.execute(S.FOLDER_DATA_TEMPLATE_SQL)
            conn.execute(S.FOLDER_DATA_INFO_SQL)
            conn.execute(S.TEMPLATE_INFO_SQL)
            for control in controls:
                conn.execute(S.INSERT_TEMPLATE_ROW, S.template_row_values(control))
            conn.execute(
                f"INSERT INTO {C.TEMPLATE_INFO} (VersionCompatabily, BackwardsCompatibility, Standard) "
                "VALUES (?,?,?)",
                (C.CREATED_VERSION, C.BACKWARDS_COMPATIBLE, ""),
            )
    finally:
        conn.close()
    return controls


def scan_media(root: Path) -> list[tuple[str, str]]:
    """(RelativePath with backslashes, File) for every image/video under root, sorted."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in C.SKIPPED_FOLDERS and not d.startswith("."))
        rel = Path(dirpath).relative_to(root)
        rel_text = "" if str(rel) == "." else "\\".join(rel.parts)
        for name in sorted(filenames):
            if Path(name).suffix.lower() in C.IMAGE_EXTENSIONS | C.VIDEO_EXTENSIONS:
                found.append((rel_text, name))
    return found


def create_data_file(ddb_path: Path, template_path: Path, progress=None) -> int:
    """Create a .ddb next to the images from a .tdb and load every file under the .ddb's folder.

    Returns the number of files added.
    """
    ddb_path, template_path = Path(ddb_path), Path(template_path)
    if ddb_path.exists():
        raise FileExistsError(ddb_path)
    root = ddb_path.parent
    tconn = sqlite3.connect(f"file:{template_path}?mode=ro", uri=True)
    tconn.row_factory = sqlite3.Row
    try:
        template_rows = [dict(r) for r in tconn.execute(
            f"SELECT * FROM {C.TEMPLATE_TABLE} ORDER BY ControlOrder")]
        folder_template = [dict(r) for r in tconn.execute(
            f"SELECT * FROM {C.FOLDER_DATA_TEMPLATE} ORDER BY ControlOrder")] if _has_table(
            tconn, C.FOLDER_DATA_TEMPLATE) else []
        folder_info = [dict(r) for r in tconn.execute(
            f"SELECT * FROM {C.FOLDER_DATA_INFO} ORDER BY Level")] if _has_table(
            tconn, C.FOLDER_DATA_INFO) else []
        standard = ""
        if _has_table(tconn, C.TEMPLATE_INFO):
            row = tconn.execute(f"SELECT * FROM {C.TEMPLATE_INFO}").fetchone()
            if row is not None and "Standard" in row.keys():
                standard = row["Standard"] or ""
    finally:
        tconn.close()

    from .template import control_from_row
    controls = [control_from_row(r) for r in template_rows]
    media = scan_media(root)

    conn = sqlite3.connect(ddb_path)
    try:
        with conn:
            conn.execute(S.TEMPLATE_TABLE_SQL)
            for row in template_rows:
                conn.execute(S.INSERT_TEMPLATE_ROW, (
                    row.get("ControlOrder"), row.get("SpreadsheetOrder"), row.get("Type"),
                    row.get("DefaultValue"), row.get("Label"), row.get("DataLabel"), row.get("Tooltip"),
                    row.get("Visible"), row.get("List"), row.get("ExportToCSV", "true"),
                    row.get("TXTBOXWIDTH"), row.get("Copyable"),
                ))
            conn.execute(S.FOLDER_DATA_TEMPLATE_SQL)
            for row in folder_template:
                conn.execute(
                    f"INSERT INTO {C.FOLDER_DATA_TEMPLATE} (ControlOrder, SpreadsheetOrder, Level, Type, "
                    "DefaultValue, Label, DataLabel, Tooltip, Visible, List, ExportToCSV) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    tuple(row.get(k) for k in ("ControlOrder", "SpreadsheetOrder", "Level", "Type",
                                               "DefaultValue", "Label", "DataLabel", "Tooltip",
                                               "Visible", "List", "ExportToCSV")))
            conn.execute(S.FOLDER_DATA_INFO_SQL)
            for row in folder_info:
                conn.execute(f"INSERT INTO {C.FOLDER_DATA_INFO} (Id, Level, Guid, Alias) VALUES (?,?,?,?)",
                             (row.get("Level"), row.get("Level"), row.get("Guid"), row.get("Alias")))

            columns = ", ".join(S.data_column_sql(c) for c in controls)
            conn.execute(f"CREATE TABLE {C.DATA_TABLE} (Id INTEGER PRIMARY KEY AUTOINCREMENT, {columns})")
            for name, cols in S.DATA_TABLE_INDEXES:
                conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {C.DATA_TABLE} ({cols})")

            counters = [c for c in controls if c.type == C.COUNTER]
            marker_cols = "".join(f", {S.q(c.data_label)} TEXT DEFAULT ''" for c in counters)
            conn.execute(f"CREATE TABLE {C.MARKERS_TABLE} (Id INTEGER PRIMARY KEY AUTOINCREMENT{marker_cols})")

            conn.execute(S.IMAGE_SET_SQL)
            conn.execute(
                f"INSERT INTO {C.IMAGE_SET_TABLE} (Id, RootFolder, Log, Row, VersionCompatabily, "
                "BackwardsCompatibility, SortTerms, SearchTerms, QuickPasteTerms, Standard) "
                "VALUES (1,?,?,?,?,?,?,?,?,?)",
                (root.name, "", "-1", C.CREATED_VERSION, C.BACKWARDS_COMPATIBLE, S.DEFAULT_SORT_TERMS,
                 "{}", "[]", standard),
            )

            labels = [c.data_label for c in controls]
            insert = (f"INSERT INTO {C.DATA_TABLE} ({', '.join(S.q(l) for l in labels)}) "
                      f"VALUES ({', '.join('?' for _ in labels)})")
            for index, (rel, name) in enumerate(media):
                taken = file_datetime(root / Path(*rel.split("\\")) / name if rel else root / name)
                values = []
                for c in controls:
                    if c.type == C.FILE:
                        values.append(name)
                    elif c.type == C.RELATIVE_PATH:
                        values.append(rel)
                    elif c.type == C.DATE_TIME:
                        values.append(taken.strftime(C.DATE_TIME_FORMAT))
                    else:
                        values.append(c.default_value or "")
                conn.execute(insert, values)
                if progress and index % 200 == 0:
                    progress(index, len(media))
    except Exception:
        conn.close()
        ddb_path.unlink(missing_ok=True)
        raise
    conn.close()
    return len(media)


def _has_table(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None
