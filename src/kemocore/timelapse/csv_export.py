"""CSV export in Timelapse2's layout (spec §8.1)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import constants as C
from .project import TimelapseProject

DEFAULT_CSV_NAME = "ImageData.csv"


def _field(text: str) -> str:
    if any(ch in text for ch in ('"', ",", "\r", "\n")):
        return '"' + text.replace('"', '""') + '"'
    return text


def _date_value(control_type: str, value: str, space: bool) -> str:
    if value == "":
        return ""
    formats = {
        C.DATE_TIME: C.DATE_TIME_FORMAT, C.DATE_TIME_CUSTOM: C.DATE_TIME_FORMAT,
        C.DATE_CUSTOM: C.DATE_FORMAT, C.TIME_CUSTOM: C.TIME_FORMAT,
    }
    try:
        parsed = datetime.strptime(value, formats[control_type])
    except ValueError:
        return ""
    text = parsed.strftime(formats[control_type])
    return (" " + text) if space else text


def export_csv(project: TimelapseProject, target: Path | None = None, include_root_folder: bool = True,
               space_before_dates: bool = True) -> Path:
    """Write every file's data. UTF-8 with BOM, CRLF, quoting only when needed (same as Timelapse)."""
    target = Path(target) if target else project.root / DEFAULT_CSV_NAME
    controls = sorted((c for c in project.controls if c.export_to_csv),
                      key=lambda c: (c.spreadsheet_order, c.control_order))
    root_folder = project.image_set().get("RootFolder") or project.root.name
    header = (["RootFolder"] if include_root_folder else []) + [c.data_label for c in controls]
    lines = [",".join(_field(h) for h in header)]
    offset = 0
    while True:
        rows = project.files({}, offset=offset, limit=2000)
        if not rows:
            break
        for row in rows:
            cells = [root_folder] if include_root_folder else []
            for c in controls:
                value = row["values"].get(c.data_label, "")
                if c.type in (C.DATE_TIME, C.DATE_TIME_CUSTOM, C.DATE_CUSTOM, C.TIME_CUSTOM):
                    value = _date_value(c.type, value, space_before_dates)
                cells.append(value)
            lines.append(",".join(_field(v) for v in cells))
        offset += len(rows)
    target.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8-sig", newline="")
    return target
