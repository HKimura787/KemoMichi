"""CSV export in Timelapse2's layout (spec §8.1)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from . import constants as C
from .project import TimelapseProject

if TYPE_CHECKING:
    from ..sidecar import Sidecar

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
               space_before_dates: bool = True, sidecar: Sidecar | None = None) -> Path:
    """Write every file's data. UTF-8 with BOM, CRLF, quoting only when needed (same as Timelapse)."""
    target = Path(target) if target else project.path.with_suffix(".csv")
    controls = sorted((c for c in project.controls if c.export_to_csv),
                      key=lambda c: (c.spreadsheet_order, c.control_order))
    root_folder = project.image_set().get("RootFolder") or project.root.name

    # Check if sidecar has file_rest data not represented in project controls
    control_labels = {c.data_label for c in controls}
    has_sidecar_rest = False
    sidecar_rests: dict[int, dict] = {}
    if sidecar is not None:
        sidecar_rests = sidecar.all_file_rest()
        rest_cols = sidecar.get("restColumns") or {}
        mapped_duration = rest_cols.get("duration")
        if sidecar_rests and (not mapped_duration or mapped_duration not in control_labels):
            has_sidecar_rest = True

    header = (["RootFolder"] if include_root_folder else []) + [c.data_label for c in controls]
    if has_sidecar_rest:
        header.append("StayDuration_sec")

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
            if has_sidecar_rest:
                file_id = row.get("id") or row.get("Id")
                rest_info = sidecar_rests.get(file_id) if file_id else None
                cells.append(rest_info["duration_seconds"] if rest_info else "")
            lines.append(",".join(_field(v) for v in cells))
        offset += len(rows)
    target.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8-sig", newline="")

    # Also export Intervals.csv if sidecar has intervals
    if sidecar is not None and hasattr(sidecar, "intervals"):
        all_intervals = sidecar.intervals()
        if all_intervals:
            int_csv = target.with_name(f"{target.stem}_intervals.csv")
            int_header = ["id", "file_id", "kind", "start_frame", "end_frame",
                          "start_seconds", "end_seconds", "duration_seconds",
                          "species", "individual", "note", "created_at"]
            int_lines = [",".join(_field(h) for h in int_header)]
            for it in all_intervals:
                row_vals = [str(it.get(k) or "") for k in int_header]
                int_lines.append(",".join(_field(v) for v in row_vals))
            int_csv.write_text("\r\n".join(int_lines) + "\r\n", encoding="utf-8-sig", newline="")

    return target
