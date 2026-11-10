import hashlib
import sqlite3

import pytest

from kemocore.timelapse import constants as C
from kemocore.timelapse.project import ProjectError, TimelapseProject, format_marker_points, parse_marker_points
from kemocore.timelapse.template import Choices, ValueError_


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_opening_and_reading_never_changes_the_file(demo):
    before = digest(demo)
    project = TimelapseProject(demo)
    project.info()
    project.files({"folder": "CamA"}, 0, 50)
    project.folders()
    project.detections(1)
    project.markers(1)
    project.close()
    assert digest(demo) == before


def test_created_file_matches_timelapse_layout(demo):
    conn = sqlite3.connect(demo)
    standard = conn.execute(
        "SELECT Type, Label, DataLabel, DefaultValue, TXTBOXWIDTH, ExportToCSV, ControlOrder, SpreadsheetOrder "
        "FROM TemplateTable WHERE Type IN ('File','RelativePath','DateTime','DeleteFlag') ORDER BY ControlOrder"
    ).fetchall()
    assert [r[0] for r in standard] == ["File", "RelativePath", "DateTime", "DeleteFlag"]
    assert standard[3][1:3] == ("Delete?", "DeleteFlag")
    assert standard[3][5] == "false" and standard[0][6] == 0
    image_set = conn.execute("SELECT RootFolder, Row, VersionCompatabily, BackwardsCompatibility, "
                             "QuickPasteTerms, SearchTerms FROM ImageSetTable").fetchone()
    assert image_set == ("project", "-1", C.CREATED_VERSION, C.BACKWARDS_COMPATIBLE, "[]", "{}")
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"IndexRelativePath", "IndexFile", "IndexRelativePathFile", "IndexRelativePathDateTimeFile",
            "IndexDeleteFlag"} <= indexes
    assert "TemplateInfo" not in {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    rel = conn.execute("SELECT DISTINCT RelativePath FROM DataTable").fetchall()
    assert ("CamA\\2026-04",) in rel
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"


def test_update_validates_normalizes_and_undoes(demo):
    project = TimelapseProject(demo)
    batch = project.update([1, 2], {"SpeciesA": "TRUE", "SpeciesACount": " 3 "})
    assert len(batch.changes) == 4
    row = project.file(1)["values"]
    assert row["SpeciesA"] == "true" and row["SpeciesACount"] == "3"
    with pytest.raises(ValueError_):
        project.update([1], {"SpeciesACount": "-1"})
    with pytest.raises(ValueError_):
        project.update([1], {"Light": "Sunny"})
    project.update([1], {"Behaviour": "Resting,Walking"})
    assert project.file(1)["values"]["Behaviour"] == "Walking,Resting"
    project.undo()
    assert project.file(1)["values"]["Behaviour"] == ""
    project.undo()
    assert project.file(1)["values"]["SpeciesA"] == "false"
    project.redo()
    assert project.file(2)["values"]["SpeciesACount"] == "3"
    with pytest.raises(ProjectError):
        project.update([1], {"File": "x.jpg"})


def test_first_write_makes_a_timelapse_style_backup(demo):
    project = TimelapseProject(demo)
    project.update([1], {"Note": "hello"})
    backups = list((demo.parent / "Backups").glob(f"{demo.stem}.*.ddb"))
    assert len(backups) == 1
    assert backups[0].name.count(".") == 3  # name.yyyy-MM-dd.HH-mm-ss.ddb


def test_filters(demo):
    project = TimelapseProject(demo)
    total = project.count({})
    assert project.count({"folder": "CamA"}) + project.count({"folder": "CamB"}) == total
    project.update([1, 5], {"SpeciesB": "true"})
    assert project.ids({"anyTrue": ["SpeciesB"]}) == [1, 5]
    assert project.count({"allFalse": ["SpeciesA", "SpeciesB", "SpeciesC", "SpeciesD"]}) == total - 2
    assert project.count({"text": "NOEXIF"}) == 1
    project.update([3], {"DeleteFlag": "true"})
    assert project.ids({"deleted": True}) == [3]


def test_newer_file_opens_read_only(demo):
    conn = sqlite3.connect(demo)
    conn.execute("UPDATE ImageSetTable SET BackwardsCompatibility = '9.0.0.0'")
    conn.commit()
    conn.close()
    project = TimelapseProject(demo)
    assert project.read_only
    with pytest.raises(ProjectError):
        project.update([1], {"Note": "x"})


def test_too_old_file_is_refused(demo):
    conn = sqlite3.connect(demo)
    conn.execute("UPDATE ImageSetTable SET VersionCompatabily = '2.2.5.0'")
    conn.commit()
    conn.close()
    with pytest.raises(ProjectError) as err:
        TimelapseProject(demo)
    assert err.value.key == "error.tooOld"


def test_add_counters_updates_data_file_and_template(demo):
    project = TimelapseProject(demo)
    template = project.find_template()
    assert template is not None
    project.add_controls([{"type": "Counter", "label": "New count", "dataLabel": "NewCount"}], template)
    assert project.file(1)["values"]["NewCount"] == "0"
    conn = sqlite3.connect(demo)
    order = conn.execute("SELECT ControlOrder, SpreadsheetOrder FROM TemplateTable WHERE DataLabel='NewCount'").fetchone()
    count = conn.execute("SELECT COUNT(*) FROM TemplateTable").fetchone()[0]
    assert order == (count, count)
    marker_default = [r for r in conn.execute("PRAGMA table_info(MarkersTable)") if r[1] == "NewCount"][0][4]
    assert marker_default == "'[]'"
    tconn = sqlite3.connect(template)
    assert tconn.execute("SELECT Type FROM TemplateTable WHERE DataLabel='NewCount'").fetchone() == ("Counter",)
    # Template and data file still agree, so Timelapse will not ask to sync.
    assert project.find_template() == template


def test_markers_round_trip(demo):
    project = TimelapseProject(demo)
    project.set_markers(2, "SpeciesACount", [[0.12345, 0.5], [1, 0]])
    raw = sqlite3.connect(demo).execute("SELECT SpeciesACount, SpeciesBCount FROM MarkersTable WHERE Id = 2").fetchone()
    assert raw == ('["0.1235,0.5","1,0"]', "[]")
    assert project.markers(2)["SpeciesACount"] == [[0.1235, 0.5], [1.0, 0.0]]
    assert parse_marker_points('[{"X":0.1,"Y":0.2}]') == [[0.1, 0.2]]
    assert format_marker_points([]) == "[]"


def test_choices_serialize_like_timelapse():
    assert Choices.parse('{"IncludeEmptyChoice":false,"ChoiceListNonEmpty":[" a ","b","a",""]}').items == ["a", "b"]
    assert Choices(False, ["日", "夜"]).serialize() == '{"IncludeEmptyChoice":false,"ChoiceListNonEmpty":["日","夜"]}'
    assert Choices(True, []).serialize() == ""
    assert Choices.parse("not json").include_empty is True
