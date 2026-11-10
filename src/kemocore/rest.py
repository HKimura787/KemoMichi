"""Staying-time measurement from start (S) and end (E) frames (plan §6.3).

Durations are exact: video times come from each frame's timestamp, still-image sequences from
the DateTime of the start and end images. Results go into the columns the user mapped; those
columns are then read-only in the UI so values can only come from S/E.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from fractions import Fraction

from . import media
from .sidecar import Sidecar
from .timelapse import constants as C
from .timelapse.project import ProjectError, TimelapseProject

SETTINGS_KEY = "restColumns"
MULTI_MODES = ("first", "sum", "list")


def column_settings(sidecar: Sidecar) -> dict:
    settings = sidecar.get(SETTINGS_KEY) or {}
    return {
        "start": settings.get("start") or None,
        "end": settings.get("end") or None,
        "duration": settings.get("duration") or None,
        "multi": settings.get("multi") if settings.get("multi") in MULTI_MODES else "first",
    }


def locked_columns(sidecar: Sidecar) -> set[str]:
    settings = column_settings(sidecar)
    return {settings[k] for k in ("start", "end", "duration") if settings[k]}


def video_interval(project: TimelapseProject, file_id: int, start_frame: int, end_frame: int) -> dict:
    row = project.file(file_id)
    if row is None:
        raise ProjectError("error.notFound", path=str(file_id))
    info = media.video_info(project.media_path(row))
    if not info.get("available") or not info.get("frameTicks"):
        raise ProjectError("error.videoUnreadable")
    if end_frame < start_frame:
        start_frame, end_frame = end_frame, start_frame
    start = media.frame_seconds(info, start_frame)
    end = media.frame_seconds(info, end_frame)
    return {
        "kind": "video", "file_id": file_id, "start_frame": start_frame, "end_frame": end_frame,
        "start_seconds": media.format_seconds(start), "end_seconds": media.format_seconds(end),
        "duration_seconds": media.format_seconds(end - start),
    }


def sequence_interval(project: TimelapseProject, start_file_id: int, end_file_id: int) -> dict:
    a, b = project.file(start_file_id), project.file(end_file_id)
    if a is None or b is None:
        raise ProjectError("error.notFound", path=f"{start_file_id}-{end_file_id}")
    ta = _parse(a["values"].get(C.DATE_TIME, ""))
    tb = _parse(b["values"].get(C.DATE_TIME, ""))
    if ta is None or tb is None:
        raise ProjectError("error.datetime")
    if tb < ta:
        a, b, ta, tb = b, a, tb, ta
        start_file_id, end_file_id = end_file_id, start_file_id
    duration = Fraction(int((tb - ta).total_seconds()))
    return {
        "kind": "sequence", "file_id": start_file_id, "start_file_id": start_file_id, "end_file_id": end_file_id,
        "start_seconds": "0", "end_seconds": media.format_seconds(duration),
        "duration_seconds": media.format_seconds(duration),
    }


def _parse(text: str) -> datetime | None:
    try:
        return datetime.strptime(text, C.DATE_TIME_FORMAT)
    except ValueError:
        return None


def _format_for(control_type: str, base: datetime | None, seconds: str) -> str:
    """Write an offset in the target column's own format."""
    if control_type in (C.DATE_TIME_CUSTOM, C.TIME_CUSTOM) and base is not None:
        moment = base + timedelta(seconds=float(seconds))
        return moment.strftime(C.DATE_TIME_FORMAT if control_type == C.DATE_TIME_CUSTOM else C.TIME_FORMAT)
    if control_type in (C.INTEGER_ANY, C.INTEGER_POSITIVE, C.COUNTER):
        return str(round(float(seconds)))
    return seconds


def write_columns(project: TimelapseProject, sidecar: Sidecar, file_id: int) -> dict:
    """Recompute the mapped columns of one file from its intervals. Returns the values written."""
    settings = column_settings(sidecar)
    targets = {k: settings[k] for k in ("start", "end", "duration") if settings[k] in project.by_label}
    intervals = [i for i in sidecar.intervals(file_id) if i["file_id"] == file_id]
    intervals.sort(key=lambda i: Fraction(i["start_seconds"] or "0"))

    if not intervals:
        sidecar.delete_file_rest(file_id)
        if targets:
            values = {label: "" for label in targets.values()}
            project.update([file_id], values, description="rest")
            return values
        return {}

    # Always persist summary to sidecar so staying time is stored even if tdb has no matching column.
    total = sum((Fraction(i["duration_seconds"]) for i in intervals), Fraction(0))
    first_start = intervals[0]["start_seconds"]
    last_end = intervals[-1]["end_seconds"]
    dur_str = media.format_seconds(total)
    sidecar.save_file_rest(file_id, first_start, last_end, dur_str, len(intervals))

    if not targets:
        return {}

    row = project.file(file_id)
    if row is None:
        return {}
    base = _parse(row["values"].get(C.DATE_TIME, ""))
    mode = settings["multi"]
    values: dict[str, str] = {}
    for key, label in targets.items():
        ctype = project.by_label[label].type
        list_ok = ctype in (C.NOTE, C.MULTI_LINE)
        if mode == "list" and list_ok:
            values[label] = ";".join(_format_for(ctype, base, i[f"{key}_seconds"]) for i in intervals)
        elif mode == "sum" and key == "duration":
            values[label] = _format_for(ctype, base, dur_str)
        elif mode == "sum" and key == "end":
            values[label] = _format_for(ctype, base, last_end)
        else:
            values[label] = _format_for(ctype, base, intervals[0][f"{key}_seconds"])
    project.update([file_id], values, description="rest")
    return values
