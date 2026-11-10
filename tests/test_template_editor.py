import copy
import shutil
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from kemocore.demo import make_image
from kemocore.timelapse.create import create_template
from kemocore.timelapse.csv_export import export_csv
from kemocore.timelapse.template import Control
from kemocore.timelapse.template_edit import read_template
from kemoserver.app import create_app
from kemoserver.security import ServerConfig


def field(kind="Note", label="Field", default="", **kwargs):
    return {"id": -1, "type": kind, "label": label, "dataLabel": label,
            "defaultValue": default, **kwargs}


@pytest.fixture
def editor(tmp_path):
    source_folder = tmp_path / "templates #日本語"
    source_folder.mkdir()
    source = source_folder / "調査.tdb"
    create_template(source, [Control(0, 0, 0, "Note", "before", "元の項目", "Original", "", True, "", True, "100", True),
                             Control(0, 0, 0, "Note", "", "削除する項目", "RemoveMe", "", True, "", True, "100", True)])
    with sqlite3.connect(source) as conn:
        conn.execute("UPDATE TemplateInfo SET Standard = 'survey-standard'")
        conn.execute("CREATE TABLE ExtraMetadata (value TEXT)")
        conn.execute("INSERT INTO ExtraMetadata VALUES ('preserve this')")
        conn.execute("INSERT INTO FolderDataTemplateTable (ControlOrder, SpreadsheetOrder, Level, Type, "
                     "DefaultValue, Label, DataLabel, Tooltip, Visible, List, ExportToCSV) "
                     "VALUES (0, 1, 1, 'Note', '', '調査地', 'Site', '', 'true', '', 'true')")
        conn.execute("INSERT INTO FolderDataInfo (Level, Guid, Alias) VALUES (1, 'guid', '調査地')")
    root = tmp_path / "images"
    root.mkdir()
    make_image(root / "sample.jpg", None, "sample")
    app = create_app(ServerConfig(roots=[tmp_path]))
    try:
        with TestClient(app) as client:
            preview = client.get("/api/template", params={"path": str(source), "folder": str(root)})
            assert preview.status_code == 200, preview.text
            yield client, root, source, preview.json(), app
    finally:
        app.state.workspace.close()


def draft(preview, name="新しい調査"):
    return {"name": name, "revision": preview["revision"], "controls": copy.deepcopy(preview["controls"])}


def wait(client, response):
    assert response.status_code == 200, response.text
    for _ in range(200):
        job = client.get(f"/api/jobs/{response.json()['id']}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.01)
    pytest.fail("Project creation did not finish")


def test_preview_and_confirmation_write_nothing(editor):
    client, root, source, preview, _ = editor
    original = source.read_bytes()
    body = {"folder": str(root), "template": str(source), "draft": draft(preview)}
    response = client.post("/api/template/validate", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["templatePath"] == str(root / "新しい調査.tdb")
    assert response.json()["ddbPath"] == str(root / "新しい調査.ddb")
    assert not list(root.glob("*.tdb")) and not list(root.glob("*.ddb"))
    assert source.read_bytes() == original
    assert client.get("/api/project").status_code == 409


def test_confirmed_fields_are_written_to_template_data_and_csv(editor):
    client, root, source, preview, app = editor
    original = source.read_bytes()
    edited = draft(preview)
    weather = next(control for control in edited["controls"] if control["dataLabel"] == "Original")
    weather.update(type="FixedChoice", label="天候", dataLabel="Weather", defaultValue="晴れ", choices=["晴れ", "雨"],
                   includeEmptyChoice=False, tooltip="調査時の天候", copyable=False)
    edited["controls"] = [control for control in edited["controls"] if control["standard"]]
    edited["controls"][0]["label"] = "画像ファイル"
    edited["controls"].extend([
        field("Counter", "AnimalCount", "003"),
        weather,
    ])
    # The display label may be Japanese; the CSV column name remains independent.
    edited["controls"][-1]["label"] = "天候"
    body = {"folder": str(root), "template": str(source), "draft": edited}
    confirmation = client.post("/api/template/validate", json=body)
    assert confirmation.status_code == 200, confirmation.text
    assert confirmation.json()["controls"][-2]["defaultValue"] == "3"
    job = wait(client, client.post("/api/project/create", json=body))
    assert job["status"] == "done", job
    assert job["result"] == {"path": str(root / "新しい調査.ddb"), "files": 1}
    assert source.read_bytes() == original
    project = client.get("/api/project").json()
    assert project["templatePath"] == str(root / "新しい調査.tdb")
    assert [control["dataLabel"] for control in project["controls"]] == [
        "File", "RelativePath", "DateTime", "DeleteFlag", "AnimalCount", "Weather"]
    assert project["controls"][0]["label"] == "画像ファイル"
    weather = project["controls"][-1]
    assert weather["label"] == "天候" and weather["choices"] == ["晴れ", "雨"]
    assert not weather["includeEmptyChoice"] and not weather["copyable"]
    assert client.get("/api/files/1").json()["values"]["AnimalCount"] == "3"
    assert client.get("/api/files/1").json()["values"]["Weather"] == "晴れ"
    with sqlite3.connect(root / "新しい調査.tdb") as conn:
        assert conn.execute("SELECT value FROM ExtraMetadata").fetchone()[0] == "preserve this"
        assert conn.execute("SELECT Standard FROM TemplateInfo").fetchone()[0] == "survey-standard"
    with sqlite3.connect(root / "新しい調査.ddb") as conn:
        assert conn.execute("SELECT Alias FROM FolderDataInfo").fetchone()[0] == "調査地"
        assert conn.execute("SELECT DataLabel FROM FolderDataTemplateTable").fetchone()[0] == "Site"
        assert "AnimalCount" in {row[1] for row in conn.execute("PRAGMA table_info(MarkersTable)")}
        assert "RemoveMe" not in {row[1] for row in conn.execute("PRAGMA table_info(DataTable)")}
    assert read_template(root / "新しい調査.tdb").controls[-1].default_value == "晴れ"
    csv = export_csv(app.state.workspace.project).read_text(encoding="utf-8-sig")
    assert csv.splitlines()[0].endswith("AnimalCount,Weather")
    assert "3,晴れ" in csv


@pytest.mark.parametrize("kind,default,choices", [
    ("Note", "メモ", []), ("MultiLine", "一行\n二行", []), ("Flag", "true", []),
    ("Counter", "2", []), ("IntegerAny", "-3", []), ("IntegerPositive", "3", []),
    ("DecimalAny", "-1.25", []), ("DecimalPositive", "1.25", []), ("AlphaNumeric", "ABC_1-2", []),
    ("FixedChoice", "雨", ["晴れ", "雨"]), ("MultiChoice", "歩行,採食", ["歩行", "採食"]),
    ("DateTime_", "2026-11-10 12:34:56", []), ("Date_", "2026-11-10", []), ("Time_", "12:34:56", []),
])
def test_supported_field_types_and_defaults_create_real_columns(editor, kind, default, choices):
    client, root, source, preview, _ = editor
    edited = draft(preview)
    edited["controls"].append(field(kind, "TestField", default, choices=choices))
    job = wait(client, client.post("/api/project/create", json={"folder": str(root), "template": str(source), "draft": edited}))
    assert job["status"] == "done", job
    assert client.get("/api/files/1").json()["values"]["TestField"] == default


@pytest.mark.parametrize("bad,error", [
    (field("Note", "file"), "error.duplicateField"),
    (field("Note", "select"), "error.templateDataLabel"),
    (field("Note", "日本語"), "error.templateDataLabel"),
    (field("Note", "Bad-Column"), "error.templateDataLabel"),
    (field("Counter", "Count", "-1"), "error.positive"),
    (field("IntegerAny", "Count", "1.2"), "error.integer"),
    (field("Flag", "Flagged", "yes"), "error.flag"),
    (field("FixedChoice", "Choice", "other", choices=["valid"]), "error.choice"),
    (field("FixedChoice", "Choice", "", choices=["valid"], includeEmptyChoice=False), "error.choice"),
    (field("FixedChoice", "Choice", "", choices=["same", "same"]), "error.templateChoices"),
    (field("MultiChoice", "Choice", "", choices=["one,two"]), "error.templateChoiceComma"),
    (field("Date_", "Day", "invalid"), "error.date"),
    (field("Note", "Test", width="-1"), "error.templateWidth"),
    (field("File", "AnotherFile"), "error.unknownType"),
])
def test_invalid_drafts_are_rejected_without_creating_files(editor, bad, error):
    client, root, source, preview, _ = editor
    edited = draft(preview)
    edited["controls"].append(bad)
    body = {"folder": str(root), "template": str(source), "draft": edited}
    for route in ("/api/template/validate", "/api/project/create"):
        response = client.post(route, json=body)
        assert response.status_code == 422, response.text
        assert response.json()["error"] == error
    assert not list(root.glob("*.tdb")) and not list(root.glob("*.ddb"))


@pytest.mark.parametrize("change", ["remove", "rename", "type", "default", "duplicate"])
def test_required_fields_cannot_be_removed_or_redefined(editor, change):
    client, root, source, preview, _ = editor
    edited = draft(preview)
    if change == "remove": edited["controls"].pop(0)
    if change == "rename": edited["controls"][0]["dataLabel"] = "NewFile"
    if change == "type": edited["controls"][0]["type"] = "Note"
    if change == "default": edited["controls"][0]["defaultValue"] = "another.jpg"
    if change == "duplicate": edited["controls"].append(copy.deepcopy(edited["controls"][0]))
    response = client.post("/api/project/create", json={"folder": str(root), "template": str(source), "draft": edited})
    assert response.status_code == 422
    assert response.json()["error"] == "error.templateStandard"


@pytest.mark.parametrize("name", ["../outside", "nested/name", "nested\\name", "CON", "COM1.txt", "name.ddb", "name.tdb", ".."])
def test_project_name_cannot_escape_folder_or_use_windows_reserved_names(editor, name):
    client, root, source, preview, _ = editor
    response = client.post("/api/template/validate", json={"folder": str(root), "template": str(source), "draft": draft(preview, name)})
    assert response.status_code == 422 and response.json()["error"] == "error.templateName"


def test_existing_template_and_data_are_never_overwritten(editor):
    client, root, source, preview, _ = editor
    for suffix, key in ((".tdb", "error.templateExists"), (".ddb", "error.ddbExists")):
        target = root / f"新しい調査{suffix}"
        target.write_bytes(b"existing file")
        response = client.post("/api/project/create", json={"folder": str(root), "template": str(source), "draft": draft(preview)})
        assert response.status_code == 409 and response.json()["detail"]["error"] == key
        assert target.read_bytes() == b"existing file"
        target.unlink()


def test_source_in_image_folder_gets_an_independent_template_and_ddb(editor):
    client, root, source, _, _ = editor
    local_source = root / source.name
    shutil.copy2(source, local_source)
    original = local_source.read_bytes()
    preview = client.get("/api/template", params={"path": str(local_source), "folder": str(root)}).json()
    assert preview["suggestedName"] == "調査_project"
    edited = draft(preview, preview["suggestedName"])
    job = wait(client, client.post("/api/project/create", json={"folder": str(root), "template": str(local_source), "draft": edited}))
    assert job["status"] == "done", job
    assert (root / "調査_project.ddb").exists() and (root / "調査_project.tdb").exists()
    assert local_source.read_bytes() == original


def test_source_change_in_wal_is_detected_before_creation(editor):
    client, root, source, _, _ = editor
    with sqlite3.connect(source) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        preview = client.get("/api/template", params={"path": str(source), "folder": str(root)}).json()
        main_file = source.read_bytes()
        conn.execute("UPDATE TemplateTable SET Label='Changed' WHERE DataLabel='Original'")
        conn.commit()
        assert source.read_bytes() == main_file  # the update is only in WAL
        response = client.post("/api/project/create", json={"folder": str(root), "template": str(source), "draft": draft(preview)})
        assert response.status_code == 409 and response.json()["detail"]["error"] == "error.templateChanged"
    assert not list(root.glob("*.tdb")) and not list(root.glob("*.ddb"))


def test_failed_creation_removes_only_its_new_template(editor, monkeypatch):
    client, root, source, preview, _ = editor
    before = source.read_bytes()

    def fail(*args):
        raise OSError("creation interrupted")

    monkeypatch.setattr("kemoserver.app.create_data_file", fail)
    job = wait(client, client.post("/api/project/create", json={"folder": str(root), "template": str(source), "draft": draft(preview)}))
    assert job["status"] == "failed"
    assert source.read_bytes() == before
    assert not list(root.glob("*.tdb")) and not list(root.glob("*.ddb"))


def test_preview_respects_allowed_folders(editor, tmp_path):
    client, root, _, _, _ = editor
    response = client.get("/api/template", params={"path": str(tmp_path.parent / "outside.tdb"), "folder": str(root)})
    assert response.status_code == 403
