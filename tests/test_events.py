import csv
import sqlite3

from conftest import needs_ffmpeg

from kemocore import events
from kemocore.sidecar import Sidecar
from kemocore.timelapse.project import TimelapseProject

COLUMNS = {"speciesName": "SpeciesName", "individual": "Individual", "entry": "EntrySec", "exit": "ExitSec", "exitFile": "ExitFile", "startInside": "InsideAtStart",
           "endInside": "InsideAtEnd", "duration": "StayDuration"}
PALETTE = {"items": [{"flag": f"Species{x}", "counter": f"Species{x}Count", "key": str(i + 1)}
                     for i, x in enumerate("ABCD")], "single": False}


def setup(demo):
    project = TimelapseProject(demo)
    sidecar = Sidecar(demo)
    sidecar.set(events.SETTINGS_KEY, COLUMNS)
    sidecar.set("palette", PALETTE)
    return project, sidecar


@needs_ffmpeg
def test_event_within_one_video_is_exact(demo):
    project, sidecar = setup(demo)
    video = project.ids({"text": "VID_0001"})[0]
    event = events.start_event(project, sidecar, video, 3, False, "SpeciesB")
    events.end_event(project, sidecar, event["id"], video, 33, False)
    values = project.file(video)["values"]
    # 30 frames at 30000/1001 fps is exactly 1.001 s.
    assert (values["EntrySec"], values["ExitSec"], values["StayDuration"]) == ("0.1001", "1.1011", "1.001")
    assert values["ExitFile"] == "VID_0001.MP4"
    assert values["SpeciesB"] == "true" and values["SpeciesBCount"] == "1" and values["SpeciesA"] == "false"


def test_event_across_files_records_exit_file(demo):
    project, sidecar = setup(demo)
    event = events.start_event(project, sidecar, 1, None, False, "SpeciesA")
    assert project.file(1)["values"]["ExitFile"] == ""  # still open
    assert [e["id"] for e in sidecar.open_events()] == [event["id"]]
    events.end_event(project, sidecar, event["id"], 3, None, False)
    values = project.file(1)["values"]
    assert values["ExitFile"] == "IMG_0003.JPG" and values["EntrySec"] == "0" and values["ExitSec"] == "0"
    # Across files: (T_end + exit) - (T_start + entry). Images: entry = exit = 0, T differs by 2 x 37 min 2 s.
    assert values["StayDuration"] == str(2 * 37 * 60 + 2)
    info = events.describe(project, sidecar.event(event["id"]))
    assert info["durationSeconds"] == str(2 * 37 * 60 + 2) and not info["sameFile"]
    assert sidecar.open_events() == []
    # The end file's own row is not changed: the event belongs to the row where it starts.
    assert project.file(3)["values"]["ExitFile"] == ""


def test_unobserved_entry_and_exit(demo):
    project, sidecar = setup(demo)
    event = events.start_event(project, sidecar, 1, None, True, "SpeciesA")
    events.end_event(project, sidecar, event["id"], 2, None, True)
    values = project.file(1)["values"]
    assert values["InsideAtStart"] == "true" and values["InsideAtEnd"] == "true"
    assert values["EntrySec"] == "" and values["ExitSec"] == "" and values["ExitFile"] == ""


def test_several_events_in_one_file_get_one_row_each(demo):
    project, sidecar = setup(demo)
    before = len(project.same_file_ids(1))
    first = events.start_event(project, sidecar, 1, None, False, "SpeciesA")
    second = events.start_event(project, sidecar, 1, None, False, "SpeciesC")
    rows = project.same_file_ids(1)
    assert len(rows) == before + 1 and sidecar.duplicates_of(1) == rows[1:]
    species = sorted((project.file(r)["values"]["SpeciesA"], project.file(r)["values"]["SpeciesC"]) for r in rows)
    assert species == [("false", "true"), ("true", "false")]
    # A duplicate is the same file: the event attaches to the original row whichever one is used.
    third = events.start_event(project, sidecar, rows[1], None, True, "SpeciesD")
    assert third["start_file_id"] == 1 and len(project.same_file_ids(1)) == before + 2
    for e in (second, third):
        events.delete_event(project, sidecar, e["id"])
    assert project.same_file_ids(1) == [1] and sidecar.duplicates_of(1) == []
    events.delete_event(project, sidecar, first["id"])
    assert project.file(1)["values"]["SpeciesA"] == "true"  # last state is kept; only event fields clear
    assert project.file(1)["values"]["ExitFile"] == ""


def test_event_writes_are_not_in_the_undo_history(demo):
    project, sidecar = setup(demo)
    project.update([2], {"Note": "mine"})
    events.start_event(project, sidecar, 1, None, False, "SpeciesA")
    project.undo()
    assert project.file(2)["values"]["Note"] == ""
    assert project.file(1)["values"]["SpeciesA"] == "true"


def test_continuity_warnings(demo):
    project, sidecar = setup(demo)
    other_camera = project.ids({"folder": "CamB"})[0]
    assert events.continuity_warning(project, 1, other_camera, 120) == "event.warnOtherCamera"
    assert events.continuity_warning(project, 3, 1, 120) == "event.warnBefore"
    assert events.continuity_warning(project, 1, 2, 120) == "event.warnGap"  # 37 minutes apart
    assert events.continuity_warning(project, 1, 2, 3600) is None


def test_export_events_csv(demo):
    project, sidecar = setup(demo)
    a = events.start_event(project, sidecar, 1, None, True, "SpeciesA", "1")
    events.end_event(project, sidecar, a["id"], 2, None, False)
    events.start_event(project, sidecar, 4, None, False, "SpeciesB")
    path = events.export_events_csv(project, sidecar)
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw
    rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    assert [r["Species"] for r in rows] == ["SpeciesA", "SpeciesB"]
    assert rows[0]["AlreadyInsideAtStart"] == "true" and rows[0]["EndFile"] == "IMG_0002.JPG"
    assert rows[1]["Open"] == "true"


def test_old_intervals_become_events(demo):
    path = demo.with_name(demo.name + ".kemomichi")
    path.unlink()  # the demo ships a current sidecar; this test needs a version 1 one
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta VALUES ('schema_version', '1');
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO settings VALUES ('restColumns', '{"start": "EntrySec", "end": "ExitSec", "duration": "StayDuration"}');
        CREATE TABLE intervals (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, file_id INTEGER NOT NULL,
            start_frame INTEGER, end_frame INTEGER, start_file_id INTEGER, end_file_id INTEGER, start_seconds TEXT,
            end_seconds TEXT, duration_seconds TEXT, individual TEXT NOT NULL DEFAULT '',
            species TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL);
        INSERT INTO intervals (kind, file_id, start_frame, end_frame, created_at, updated_at)
            VALUES ('video', 14, 3, 33, 'x', 'x');
    """)
    conn.commit()
    conn.close()
    sidecar = Sidecar(demo)
    migrated = sidecar.events()
    assert len(migrated) == 1 and migrated[0]["start_file_id"] == 14 and migrated[0]["end_frame"] == 33
    assert sidecar.get(events.SETTINGS_KEY)["entry"] == "EntrySec"


@needs_ffmpeg
def test_overlapping_events_in_one_video(demo):
    """Male A stays frames 1-4 and female B frames 3-6 of the same video: two events, two rows."""
    project, sidecar = setup(demo)
    video = project.ids({"text": "VID_0001"})[0]
    a = events.start_event(project, sidecar, video, 1, False, "SpeciesA")
    b = events.start_event(project, sidecar, video, 3, False, "SpeciesA")
    assert {e["id"] for e in sidecar.open_events()} == {a["id"], b["id"]}
    events.end_event(project, sidecar, a["id"], video, 4, False)
    events.end_event(project, sidecar, b["id"], video, 6, False)
    rows = [project.file(r)["values"] for r in project.same_file_ids(video)]
    # Individuals are numbered automatically across the project.
    assert [(r["Individual"], r["EntrySec"], r["ExitSec"], r["StayDuration"]) for r in rows] == [
        ("1", "0.033367", "0.133467", "0.1001"),
        ("2", "0.1001", "0.2002", "0.1001"),
    ]
    assert all(r["SpeciesA"] == "true" and r["SpeciesName"] == "SpeciesA" and r["ExitFile"] == "VID_0001.MP4"
               for r in rows)


def test_individual_numbers_are_never_reused(demo):
    project, sidecar = setup(demo)
    first = events.start_event(project, sidecar, 1, None, False, "SpeciesA")
    second = events.start_event(project, sidecar, 2, None, False, "SpeciesB")
    events.delete_event(project, sidecar, second["id"])
    third = events.start_event(project, sidecar, 3, None, False, "SpeciesB")
    named = events.start_event(project, sidecar, 4, None, False, "SpeciesB", "male A")
    assert (first["individual"], third["individual"], named["individual"]) == ("1", "3", "male A")
    assert project.file(3)["values"]["SpeciesName"] == "SpeciesB"
