"""REST events: one animal's stay in the focal area, from entry to exit (plan §6.3).

An event starts in one file (video or still image) and may end in a later file of the same camera,
because a stay can outlast one video. A temporary exit and return is two events. Either end can be
unobserved: the animal was already inside when the first file began, or still inside when the last
file ended.

The event list lives in the sidecar. Results are also written into the .ddb the way users record them
in Timelapse2: the row of the file where the event starts carries the entry time, the file it left
in and the exit time. A file with several events gets one row per event, duplicating the row as
Timelapse2's "duplicate record" does.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from fractions import Fraction
from pathlib import Path

from . import media
from .sidecar import Sidecar
from .timelapse import constants as C
from .timelapse.project import ProjectError, TimelapseProject

SETTINGS_KEY = "eventColumns"
COLUMN_KEYS = ("entry", "exit", "exitFile", "startInside", "endInside", "duration")
FLAG_KEYS = ("startInside", "endInside")
DEFAULT_CONTINUITY_GAP = 120  # seconds between consecutive videos of one stay


def column_settings(sidecar: Sidecar) -> dict:
    saved = sidecar.get(SETTINGS_KEY) or {}
    settings = {k: saved.get(k) or None for k in COLUMN_KEYS}
    settings["writeSpecies"] = bool(saved.get("writeSpecies", True))
    settings["continuityGap"] = float(saved.get("continuityGap") or DEFAULT_CONTINUITY_GAP)
    return settings


def locked_columns(sidecar: Sidecar) -> set[str]:
    """Columns filled only from events; the UI does not let people type into them."""
    settings = column_settings(sidecar)
    return {settings[k] for k in COLUMN_KEYS if settings[k]}


def original_row(project: TimelapseProject, file_id: int) -> int:
    """The first row of a file. Events always attach there, whichever duplicate was on screen."""
    ids = project.same_file_ids(file_id)
    if not ids:
        raise ProjectError("error.fileNotFound")
    return ids[0]


def _parse(text: str) -> datetime | None:
    try:
        return datetime.strptime(text, C.DATE_TIME_FORMAT)
    except (TypeError, ValueError):
        return None


def seconds_in_file(project: TimelapseProject, file_id: int, frame: int | None) -> Fraction | None:
    """Exact time of a frame from the start of its video; 0 for a still image."""
    if frame is None:
        return Fraction(0)
    row = project.file(file_id)
    if row is None:
        return None
    info = media.video_info(project.media_path(row))
    if not info.get("available") or not info.get("frameTicks"):
        return None
    return media.frame_seconds(info, frame)


def describe(project: TimelapseProject, event: dict) -> dict:
    """Everything shown and exported for an event, computed from its start and end points."""
    start_row = project.file(event["start_file_id"])
    end_row = project.file(event["end_file_id"]) if event["end_file_id"] else None
    entry = None if event["start_inside"] else seconds_in_file(project, event["start_file_id"], event["start_frame"])
    exit_ = None
    if end_row is not None and not event["end_inside"]:
        exit_ = seconds_in_file(project, event["end_file_id"], event["end_frame"])
    same_file = end_row is not None and event["end_file_id"] == event["start_file_id"]
    # Stay = (T_end + exit) - (T_start + entry), T being each file's clock time (users' REST rule).
    # Within one file the T terms cancel, leaving the exact frame-time difference.
    duration = None
    if entry is not None and exit_ is not None:
        if same_file:
            duration = exit_ - entry
        else:
            start_time = _parse(start_row["values"].get(C.DATE_TIME)) if start_row else None
            end_time = _parse(end_row["values"].get(C.DATE_TIME)) if end_row else None
            if start_time and end_time:
                duration = Fraction(int((end_time - start_time).total_seconds())) + exit_ - entry

    def file_name(row):
        return row["values"].get(C.FILE, "") if row else ""

    def folder(row):
        return row["values"].get(C.RELATIVE_PATH, "") if row else ""

    return {
        **event,
        "startFile": file_name(start_row), "startFolder": folder(start_row),
        "startDateTime": start_row["values"].get(C.DATE_TIME, "") if start_row else "",
        "endFile": file_name(end_row), "endFolder": folder(end_row),
        "endDateTime": end_row["values"].get(C.DATE_TIME, "") if end_row else "",
        "entrySeconds": None if entry is None else media.format_seconds(entry),
        "exitSeconds": None if exit_ is None else media.format_seconds(exit_),
        "sameFile": same_file,
        "durationSeconds": None if duration is None else media.format_seconds(duration),
    }


def continuity_warning(project: TimelapseProject, start_id: int, end_id: int, gap_limit: float) -> str | None:
    """Why an end file looks like it cannot continue a stay that began in the start file, if it does."""
    a, b = project.file(start_id), project.file(end_id)
    if a is None or b is None:
        return "error.fileNotFound"
    if a["values"].get(C.RELATIVE_PATH) != b["values"].get(C.RELATIVE_PATH):
        return "event.warnOtherCamera"
    ta, tb = _parse(a["values"].get(C.DATE_TIME)), _parse(b["values"].get(C.DATE_TIME))
    if ta and tb:
        if tb < ta:
            return "event.warnBefore"
        length = _file_length(project, a)
        if (tb - ta).total_seconds() - length > gap_limit and start_id != end_id:
            return "event.warnGap"
    return None


def _file_length(project: TimelapseProject, row: dict) -> float:
    path = project.media_path(row)
    if not media.is_video(path) or not path.exists():
        return 0.0
    info = media.video_info(path)
    if not info.get("frameTicks"):
        return 0.0
    return float(media.frame_seconds(info, len(info["frameTicks"]) - 1))


# ---- writing results into the data file -----------------------------------------------------

def _format_for(project: TimelapseProject, label: str, value: str | None) -> str:
    if value is None:
        return ""
    ctype = project.by_label[label].type
    if ctype in (C.INTEGER_ANY, C.INTEGER_POSITIVE, C.COUNTER):
        return str(round(float(value)))
    return value


def _event_values(project: TimelapseProject, settings: dict, palette: dict | None, event: dict | None) -> dict:
    values: dict[str, str] = {}
    info = describe(project, event) if event else None
    targets = {k: settings[k] for k in COLUMN_KEYS if settings[k] in project.by_label}
    for key, label in targets.items():
        if key in FLAG_KEYS:
            values[label] = "true" if info and info["start_inside" if key == "startInside" else "end_inside"] else "false"
        elif key == "entry":
            values[label] = _format_for(project, label, info and info["entrySeconds"])
        elif key == "exit":
            values[label] = _format_for(project, label, info and info["exitSeconds"])
        elif key == "exitFile":
            values[label] = info["endFile"] if info and info["end_file_id"] and not info["end_inside"] else ""
        elif key == "duration":  # (T_end + exit) - (T_start + entry); see describe()
            values[label] = _format_for(project, label, info and info["durationSeconds"])
    if settings["writeSpecies"] and event and palette and event.get("species"):
        for item in palette.get("items", []):
            if item["flag"] not in project.by_label:
                continue
            on = item["flag"] == event["species"]
            values[item["flag"]] = "true" if on else "false"
            if item.get("counter") in project.by_label:
                values[item["counter"]] = "1" if on else "0"
    return values


def sync_file(project: TimelapseProject, sidecar: Sidecar, file_id: int) -> dict:
    """Make the rows of one file match the events that start in it: one row per event.

    Rows KemoMichi duplicated earlier are reused or removed; the file's own rows are never deleted.
    Returns {"rows": [...ids written], "created": [...], "deleted": [...]}.
    """
    original = original_row(project, file_id)
    settings = column_settings(sidecar)
    palette = sidecar.get("palette")
    events = sidecar.events("WHERE start_file_id = ?", (original,))
    events.sort(key=lambda e: (not e["start_inside"], e["start_frame"] or 0, e["id"]))
    existing = set(project.same_file_ids(original))
    duplicates = [r for r in sidecar.duplicates_of(original) if r in existing]
    stale = [r for r in sidecar.duplicates_of(original) if r not in existing]
    if stale:
        sidecar.remove_duplicates(stale)
    rows = [original] + duplicates
    needed = max(1, len(events))
    created = []
    while len(rows) < needed:
        new_id = project.duplicate_row(original)
        sidecar.add_duplicate(new_id, original)
        rows.append(new_id)
        created.append(new_id)
    deleted = rows[needed:]
    if deleted:
        project.delete_rows(deleted)
        sidecar.remove_duplicates(deleted)
    rows = rows[:needed]
    for index, row_id in enumerate(rows):
        values = _event_values(project, settings, palette, events[index] if index < len(events) else None)
        if values:
            project.update([row_id], values, description="events", record_undo=False)
    return {"rows": rows, "created": created, "deleted": deleted}


# ---- creating and changing events -----------------------------------------------------------

def start_event(project: TimelapseProject, sidecar: Sidecar, file_id: int, frame: int | None,
                inside: bool, species: str = "", individual: str = "") -> dict:
    original = original_row(project, file_id)
    event = sidecar.save_event({
        "species": species, "individual": individual, "start_file_id": original,
        "start_frame": None if inside else frame, "start_inside": inside,
    })
    sync_file(project, sidecar, original)
    return event


def end_event(project: TimelapseProject, sidecar: Sidecar, event_id: int, file_id: int, frame: int | None,
              inside: bool) -> dict:
    event = sidecar.event(event_id)
    if event is None:
        raise ProjectError("error.notFound", path=str(event_id))
    end_file = original_row(project, file_id)
    if end_file == event["start_file_id"] and not inside and not event["start_inside"]:
        if frame is not None and event["start_frame"] is not None and frame < event["start_frame"]:
            raise ProjectError("event.endBeforeStart")
    event.update({"end_file_id": end_file, "end_frame": None if inside else frame, "end_inside": inside})
    saved = sidecar.save_event(event)
    sync_file(project, sidecar, saved["start_file_id"])
    return saved


def update_event(project: TimelapseProject, sidecar: Sidecar, event_id: int, changes: dict) -> dict:
    event = sidecar.event(event_id)
    if event is None:
        raise ProjectError("error.notFound", path=str(event_id))
    old_start = event["start_file_id"]
    for key in ("species", "individual", "note", "start_frame", "start_inside", "end_frame", "end_inside"):
        if key in changes:
            event[key] = changes[key]
    if "reopen" in changes and changes["reopen"]:
        event.update({"end_file_id": None, "end_frame": None, "end_inside": False})
    saved = sidecar.save_event(event)
    sync_file(project, sidecar, saved["start_file_id"])
    if old_start != saved["start_file_id"]:
        sync_file(project, sidecar, old_start)
    return saved


def delete_event(project: TimelapseProject, sidecar: Sidecar, event_id: int) -> dict | None:
    removed = sidecar.delete_event(event_id)
    if removed:
        sync_file(project, sidecar, removed["start_file_id"])
    return removed


def resync_all(project: TimelapseProject, sidecar: Sidecar) -> int:
    """Rewrite every file that has events (after the column settings change)."""
    starts = {e["start_file_id"] for e in sidecar.events()}
    starts |= set(sidecar.all_duplicates().values())
    for file_id in starts:
        if project.file(file_id) is not None:
            sync_file(project, sidecar, file_id)
    return len(starts)


# ---- export ---------------------------------------------------------------------------------

EXPORT_HEADER = [
    "EventId", "Species", "Individual", "StartFolder", "StartFile", "StartDateTime", "EntrySeconds",
    "AlreadyInsideAtStart", "EndFolder", "EndFile", "EndDateTime", "ExitSeconds", "StillInsideAtEnd",
    "Open", "SameFile", "DurationSeconds", "Note",
]


def export_events_csv(project: TimelapseProject, sidecar: Sidecar, target: Path | None = None) -> Path:
    """One row per event. UTF-8 with BOM and CRLF, like the Timelapse-style data CSV."""
    target = Path(target) if target else project.root / "KemoMichiEvents.csv"
    labels = {c.data_label: c.label for c in project.controls}
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(EXPORT_HEADER)
    rows = [describe(project, e) for e in sidecar.events()]
    rows.sort(key=lambda d: (d["startFolder"], d["startDateTime"], d["startFile"], d["start_frame"] or 0, d["id"]))
    for d in rows:
        writer.writerow([
            d["id"], labels.get(d["species"], d["species"]), d["individual"], d["startFolder"], d["startFile"],
            d["startDateTime"], d["entrySeconds"] or "", str(d["start_inside"]).lower(), d["endFolder"],
            d["endFile"], d["endDateTime"], d["exitSeconds"] or "", str(d["end_inside"]).lower(),
            str(d["open"]).lower(), str(d["sameFile"]).lower(), d["durationSeconds"] or "", d["note"],
        ])
    target.write_text(buffer.getvalue(), encoding="utf-8-sig", newline="")
    return target
