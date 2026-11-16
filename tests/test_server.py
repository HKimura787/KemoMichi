import base64
import json
import sqlite3
import time

from pathlib import Path

import pytest
from conftest import needs_ffmpeg
from fastapi.testclient import TestClient

import kemoserver.app as app_module
from kemocore.demo import make_image
from kemocore.timelapse.create import create_template, scan_media
from kemocore.timelapse.project import ProjectError
from kemoserver.app import create_app
from kemoserver.security import ServerConfig

# A 1x1 black pixel JPEG, as the capture endpoint receives it from the browser (a data URL).
FAKE_IMAGE_BYTES = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////"
    "////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
)
FAKE_IMAGE_DATA_URL = "data:image/jpeg;base64," + base64.b64encode(FAKE_IMAGE_BYTES).decode()


@pytest.fixture
def client(demo):
    app = create_app(ServerConfig(open_path=demo))
    with TestClient(app) as c:
        yield c


def test_project_and_files(client):
    project = client.get("/api/project").json()
    on_disk = len(scan_media(Path(project["root"])))  # 25 images, plus 2 videos when ffmpeg made them
    assert project["total"] == on_disk and project["name"] == "TimelapseTemplate.ddb"
    assert project["templatePath"].endswith("TimelapseTemplate.tdb")
    page = client.get("/api/files", params={"filter": json.dumps({"folder": "CamB"}), "limit": 5}).json()
    cam_b = len([m for m in scan_media(Path(project["root"])) if m[0].startswith("CamB")])
    assert page["total"] == cam_b and len(page["rows"]) == 5
    detail = client.get(f"/api/files/{page['rows'][0]['id']}").json()
    assert detail["kind"] == "image" and detail["exists"]


@pytest.mark.parametrize("external_template", [False, True])
def test_create_uses_template_name_and_refuses_overwrite(tmp_path, external_template):
    root = tmp_path / "images"
    root.mkdir()
    template_folder = tmp_path if external_template else root
    template = template_folder / "調査 2026.11.tdb"
    create_template(template)
    make_image(root / "sample.JPG", None, "sample")
    legacy_ddb = root / "TimelapseData.ddb"
    legacy_ddb.write_bytes(b"existing data")
    app = create_app(ServerConfig(roots=[tmp_path]))
    try:
        with TestClient(app) as c:
            response = c.post("/api/project/create", json={"folder": str(root), "template": str(template)})
            assert response.status_code == 200
            job_id = response.json()["id"]
            for _ in range(200):
                job = c.get(f"/api/jobs/{job_id}").json()
                if job["status"] != "running":
                    break
                time.sleep(0.01)
            assert job["status"] == "done", job
            ddb = root / "調査 2026.11.ddb"
            assert job["result"] == {"path": str(ddb), "files": 1}
            project = c.get("/api/project").json()
            assert project["path"] == str(ddb) and project["total"] == 1
            assert project["templatePath"] == str(root / template.name)
            assert legacy_ddb.read_bytes() == b"existing data"

            before = ddb.read_bytes()
            duplicate = c.post("/api/project/create", json={"folder": str(root), "template": str(template)})
            assert duplicate.status_code == 409
            assert duplicate.json()["detail"] == {"error": "error.ddbExists", "params": {"path": str(ddb)}}
            assert ddb.read_bytes() == before
    finally:
        app.state.workspace.close()


def test_edit_undo_and_validation(client):
    r = client.patch("/api/files", json={"ids": [1, 2], "values": {"SpeciesA": True, "SpeciesACount": "2"}})
    assert r.status_code == 200 and r.json()["changed"] == 4
    bad = client.patch("/api/files", json={"ids": [1], "values": {"SpeciesACount": "x"}})
    assert bad.status_code == 422 and bad.json()["error"] == "error.integer"
    undone = client.post("/api/undo").json()
    assert undone["fileIds"] == [1, 2]
    assert client.get("/api/files/1").json()["values"]["SpeciesA"] == "false"


def test_media(client):
    thumb = client.get("/api/media/1/thumb")
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"
    assert client.get("/api/media/1/preview").status_code == 200


@needs_ffmpeg
def test_video_range_and_info(client):
    vid = client.get("/api/files/ids", params={"filter": json.dumps({"text": "VID_0002"})}).json()[0]
    info = client.get(f"/api/media/{vid}/video-info").json()
    assert info["available"] and len(info["frameTimes"]) == 45 and info["frameTimes"][1] == pytest.approx(1 / 15)
    part = client.get(f"/api/media/{vid}/video", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100


def test_events_lock_their_columns_and_duplicate_rows(client):
    client.put("/api/settings/eventColumns", json={"value": {
        "entry": "EntrySec", "exit": "ExitSec", "exitFile": "ExitFile", "startInside": "InsideAtStart",
        "endInside": "InsideAtEnd", "duration": "StayDuration"}})
    first = client.post("/api/events", json={"fileId": 1, "inside": True, "species": "SpeciesA"}).json()
    assert [e["id"] for e in first["open"]] == [first["event"]["id"]]
    ended = client.post(f"/api/events/{first['event']['id']}/end", json={"fileId": 2, "frame": None}).json()
    assert ended["event"]["endFile"] == "IMG_0002.JPG" and ended["open"] == []
    row = client.get("/api/files/1").json()
    assert row["values"]["ExitFile"] == "IMG_0002.JPG" and row["values"]["InsideAtStart"] == "true"
    locked = client.patch("/api/files", json={"ids": [1], "values": {"ExitFile": "x"}})
    assert locked.status_code == 400 and locked.json()["detail"]["error"] == "error.lockedField"
    second = client.post("/api/events", json={"fileId": 1, "frame": None, "species": "SpeciesB"}).json()
    assert len(row["sameFileRows"]) == 1 and len(client.get("/api/files/1").json()["sameFileRows"]) == 2
    client.delete(f"/api/events/{second['event']['id']}")
    assert len(client.get("/api/files/1").json()["sameFileRows"]) == 1
    assert client.post("/api/export/events").json()["path"].endswith("KemoMichiEvents.csv")


def test_species_counters_and_palette(client):
    suggestion = client.get("/api/palette/suggest").json()
    assert suggestion["items"][0] == {"flag": "SpeciesA", "counter": "SpeciesACount", "key": "1"}
    result = client.post("/api/template/species-counters", json={"flags": ["Unclear"], "labelSuffix": " count"}).json()
    assert result["templateUpdated"] is True
    assert any(c["dataLabel"] == "UnclearCount" for c in result["controls"])


def test_folders_and_guides(client):
    client.put("/api/folder-settings", json={"folder": "CamA", "key": "guides",
                                             "value": [{"shape": "triangle", "points": [[0.2, 0.9], [0.5, 0.3], [0.8, 0.9]]}]})
    got = client.get("/api/folder-settings", params={"folder": "CamA\\2026-04"}).json()
    assert got["guides"][0]["shape"] == "triangle" and got["color"] is None


def test_server_mode_requires_password_and_roots(tmp_path):
    with pytest.raises(SystemExit):
        ServerConfig(host="0.0.0.0").check()
    with pytest.raises(SystemExit):
        ServerConfig(host="0.0.0.0", password="x").check()
    ServerConfig(host="0.0.0.0", password="x", roots=[tmp_path]).check()


def test_password_and_root_restriction(demo, tmp_path):
    app = create_app(ServerConfig(host="0.0.0.0", password="secret", roots=[demo.parent]))
    with TestClient(app) as c:  # the test client is not a loopback peer
        assert c.get("/api/info").status_code == 401
        auth = {"Authorization": "Basic " + base64.b64encode(b"user:secret").decode()}
        assert c.get("/api/info", headers=auth).status_code == 200
        outside = c.get("/api/browse", params={"path": str(tmp_path)}, headers=auth)
        assert outside.status_code == 403
        inside = c.get("/api/browse", params={"path": str(demo.parent)}, headers=auth).json()
        assert any(f["kind"] == "ddb" for f in inside["files"])


def test_capture_and_file_rest(client):
    # Test file_detail returns fileRest (this does not depend on the file being a video)
    detail = client.get("/api/files/1").json()
    assert detail["kind"] == "image"
    assert "fileRest" in detail

    # Test save capture endpoint: the saved file matches exactly what was sent.
    res = client.post("/api/capture", json={"fileId": 1, "filename": "test_shot.jpg", "image": FAKE_IMAGE_DATA_URL})
    assert res.status_code == 200
    data = res.json()
    saved = Path(data["path"])
    assert saved.exists()
    assert saved.read_bytes() == FAKE_IMAGE_BYTES
    assert data["filename"] == "test_shot.jpg"
    assert data["relative"] == f"captures/{saved.name}"


@needs_ffmpeg
def test_capture_and_file_rest_for_video(client):
    # Video-specific: fileRest is also present on a video row, and capture works from one.
    vid = client.get("/api/files/ids", params={"filter": json.dumps({"text": "VID_0001"})}).json()[0]
    detail = client.get(f"/api/files/{vid}").json()
    assert detail["kind"] == "video"
    assert "fileRest" in detail
    res = client.post("/api/capture", json={"fileId": vid, "filename": "video_shot.jpg", "image": FAKE_IMAGE_DATA_URL})
    assert res.status_code == 200
    assert Path(res.json()["path"]).read_bytes() == FAKE_IMAGE_BYTES


def test_capture_rejects_when_project_is_read_only(client, demo):
    opened = client.post("/api/project/open", json={"path": str(demo), "readOnly": True}).json()
    assert opened["readOnly"] is True
    res = client.post("/api/capture", json={"fileId": 1, "filename": "ro.jpg", "image": FAKE_IMAGE_DATA_URL})
    assert res.status_code == 400
    assert res.json()["error"] == "readOnly.requested"
    assert not (demo.parent / "captures").exists()


@pytest.mark.parametrize("bad_image", ["not-valid-base64!!!", "", "data:image/jpeg;base64,"])
def test_capture_rejects_invalid_or_empty_base64(client, demo, bad_image):
    res = client.post("/api/capture", json={"fileId": 1, "filename": "bad.jpg", "image": bad_image})
    assert res.status_code == 422
    assert res.json()["detail"]["error"] == "error.badImage"
    assert not (demo.parent / "captures").exists()


def test_capture_rejects_oversized_image(client, demo, monkeypatch):
    monkeypatch.setattr(app_module, "MAX_CAPTURE_IMAGE_BYTES", 4)
    res = client.post("/api/capture", json={"fileId": 1, "filename": "big.jpg", "image": FAKE_IMAGE_DATA_URL})
    assert res.status_code == 413
    assert res.json()["detail"]["error"] == "error.imageTooLarge"
    assert not (demo.parent / "captures").exists()


def test_capture_filename_blocks_path_traversal(client, demo):
    res = client.post("/api/capture", json={"fileId": 1, "filename": "../../evil.jpg", "image": FAKE_IMAGE_DATA_URL})
    assert res.status_code == 200
    saved = Path(res.json()["path"])
    assert saved.parent == demo.parent / "captures"
    assert saved.name == "evil.jpg"
    assert not (demo.parent.parent / "evil.jpg").exists()
    assert not (demo.parent / "evil.jpg").exists()


def test_capture_duplicate_filename_gets_suffixed_without_overwrite(client):
    res1 = client.post("/api/capture", json={"fileId": 1, "filename": "dup.jpg", "image": FAKE_IMAGE_DATA_URL})
    res2 = client.post("/api/capture", json={"fileId": 1, "filename": "dup.jpg", "image": FAKE_IMAGE_DATA_URL})
    assert res1.status_code == 200 and res2.status_code == 200
    first, second = Path(res1.json()["path"]), Path(res2.json()["path"])
    assert first != second
    assert first.name == "dup.jpg"
    assert second.name == "dup_1.jpg"
    assert first.exists() and second.exists()
    assert first.read_bytes() == second.read_bytes() == FAKE_IMAGE_BYTES


def test_duplicate_file_api(client):
    detail_before = client.get("/api/files/1").json()
    assert detail_before["recordIndex"] == 1
    assert detail_before["recordTotal"] == 1

    res = client.post("/api/files/1/duplicate")
    assert res.status_code == 200
    data = res.json()
    new_id = data["id"]
    assert new_id != 1

    detail_after = client.get("/api/files/1").json()
    assert detail_after["recordIndex"] == 1
    assert detail_after["recordTotal"] == 2

    dup_detail = client.get(f"/api/files/{new_id}").json()
    assert dup_detail["recordIndex"] == 2
    assert dup_detail["recordTotal"] == 2
    assert dup_detail["values"]["File"] == detail_before["values"]["File"]

    # 404 for non-existent file
    assert client.post("/api/files/999999/duplicate").status_code == 404

def _tree(client, flt=None):
    params = {"filter": json.dumps(flt)} if flt else {}
    return client.get("/api/files/tree", params=params).json()


def test_file_tree_lists_each_file_once_in_list_order(client):
    project = client.get("/api/project").json()
    media = scan_media(Path(project["root"]))  # independent of the database: what is on disk
    tree = _tree(client)
    assert tree["folders"] == ["CamA\\2026-04", "CamB\\2026-04"]
    assert len(tree["files"]) == len(media)
    assert [f[0] for f in tree["files"]] == client.get("/api/files/ids").json()
    on_disk = sorted((rel.replace("/", "\\").strip("\\"), name) for rel, name, *_ in media)
    assert sorted((tree["folders"][f[1]], f[2]) for f in tree["files"]) == on_disk
    assert {(f[3], f[4]) for f in tree["files"]} == {(0, 1)}  # the demo starts with nothing entered, one record each


def test_file_tree_state_bits_follow_species_and_delete_flag(client):
    flag = client.get("/api/project").json()["settings"]["palette"]["items"][0]["flag"]
    ids = client.get("/api/files/ids").json()
    assert client.patch("/api/files", json={"ids": [ids[0]], "values": {flag: "true"}}).status_code == 200
    assert client.patch("/api/files", json={"ids": [ids[1]], "values": {"DeleteFlag": "true"}}).status_code == 200
    assert client.patch("/api/files", json={"ids": [ids[2]], "values": {flag: "true", "DeleteFlag": "true"}}).status_code == 200
    state = {f[0]: f[3] for f in _tree(client)["files"]}
    assert [state[i] for i in ids[:4]] == [1, 2, 3, 0]


def test_file_tree_follows_the_filter_and_skips_duplicated_rows(client):
    project = client.get("/api/project").json()
    cam_b = len([m for m in scan_media(Path(project["root"])) if m[0].startswith("CamB")])
    narrowed = _tree(client, {"folder": "CamB"})
    assert narrowed["folders"] == ["CamB\\2026-04"] and len(narrowed["files"]) == cam_b
    assert _tree(client, {"text": "no-such-file-zzz"}) == {"folders": [], "files": []}
    first = client.get("/api/files/ids").json()[0]
    assert client.post(f"/api/files/{first}/duplicate").status_code == 200
    after = _tree(client)["files"]
    assert len(after) == project["total"]  # a second record is not a second file
    assert [f[0] for f in after if f[4] != 1] == [first] and after[0][4] == 2  # it is counted on the file
    # a filter only the second record passes still lists the file once, under that record
    flag = project["settings"]["palette"]["items"][0]["flag"]
    second = client.get(f"/api/files/{first}").json()["sameFileRows"][1]
    assert client.patch("/api/files", json={"ids": [second], "values": {flag: "true"}}).status_code == 200
    assert [f[0] for f in _tree(client, {"anyTrue": [flag]})["files"]] == [second]


def test_file_tree_with_records_lists_a_file_only_a_duplicated_row_of_which_passes(client):
    # Two stays on file 1: KemoMichi keeps the second on a row it duplicated (hidden from the file list).
    client.post("/api/events", json={"fileId": 1, "inside": True, "species": "SpeciesA"})
    second = client.post("/api/events", json={"fileId": 1, "species": "SpeciesB"}).json()
    assert list(second["duplicates"].values()) == [1]
    extra = int(next(iter(second["duplicates"])))
    values = client.get(f"/api/files/{extra}").json()["values"]
    own = client.get("/api/files/1").json()["values"]
    flags = [i["flag"] for i in client.get("/api/project").json()["settings"]["palette"]["items"]]
    only_extra = [f for f in flags if values[f] == "true" and own[f] != "true"]
    assert len(only_extra) == 1
    flt = {"anyTrue": only_extra}
    assert _tree(client, flt)["files"] == []  # the file list has no such stop
    listed = client.get("/api/files/tree", params={"filter": json.dumps(flt), "records": "true"}).json()
    assert [f[0] for f in listed["files"]] == [extra]
    assert [f[0] for f in listed["files"]] == client.get("/api/files/ids", params={"filter": json.dumps(flt), "records": "true"}).json()
    assert listed["files"][0][4] == 2  # both rows of the file are counted
    # without a filter the file is still one entry, in either view
    assert len(client.get("/api/files/tree", params={"records": "true"}).json()["files"]) == client.get("/api/project").json()["total"] - 1


def test_file_tree_top_level_files_missing_folder_and_deep_folders(client):
    project = client.get("/api/project").json()
    ids = client.get("/api/files/ids").json()
    top, null, deep = ids[3], ids[7], ids[1]
    with sqlite3.connect(Path(project["root"]) / project["name"]) as db:
        db.execute("UPDATE DataTable SET RelativePath = '' WHERE Id = ?", (top,))
        db.execute("UPDATE DataTable SET RelativePath = NULL WHERE Id = ?", (null,))
        db.execute("UPDATE DataTable SET RelativePath = 'CamA\\2026-04\\night\\late' WHERE Id = ?", (deep,))
    tree = _tree(client)
    assert tree["folders"] == ["", "CamA\\2026-04", "CamA\\2026-04\\night\\late", "CamB\\2026-04"]
    assert {f[0] for f in tree["files"] if f[1] == 0} == {top, null}  # no folder and an empty one are both the top level
    assert [f[0] for f in tree["files"] if f[1] == 2] == [deep]
    assert [f[0] for f in tree["files"]] == client.get("/api/files/ids").json()  # still the order next / previous walks
    assert len(tree["files"]) == project["total"]


@pytest.mark.parametrize("palette", [
    {"items": [{"flag": 'x"; DROP TABLE DataTable; --', "counter": "", "key": "1"}]},  # not a column: never reaches the SQL
    {"items": ["SpeciesA", None, 3, {"flag": 7}, {"flag": ["SpeciesA"]}, {}]},
    {"items": "SpeciesA"},
    {"items": None},
    ["SpeciesA"],
])
def test_file_tree_survives_a_broken_palette(client, palette):
    total = client.get("/api/project").json()["total"]
    client.app.state.workspace.sidecar.set("palette", palette)
    response = client.get("/api/files/tree")
    assert response.status_code == 200
    assert len(response.json()["files"]) == total
    assert {f[3] for f in response.json()["files"]} == {0}
    assert len(client.get("/api/files/ids").json()) == total  # the table is still there


def test_file_tree_ignores_broken_palette_items_but_keeps_the_good_one(client):
    flag = client.get("/api/project").json()["settings"]["palette"]["items"][0]["flag"]
    first = client.get("/api/files/ids").json()[0]
    assert client.patch("/api/files", json={"ids": [first], "values": {flag: "true"}}).status_code == 200
    client.app.state.workspace.sidecar.set("palette", {"items": [None, {"flag": "NoSuchColumn"}, {"flag": flag}]})
    assert [f[0] for f in _tree(client)["files"] if f[3] == 1] == [first]


# ---- a project whose template has no species and no stay fields (settings from scratch) -------

@pytest.fixture
def bare(tmp_path):
    """Three images and the standard template only: no Flag, no Counter, nothing for stays."""
    root = tmp_path / "bare"
    (root / "CamA").mkdir(parents=True)
    for i in range(3):
        make_image(root / "CamA" / f"IMG_{i:04d}.JPG", None, str(i))
    template = root / "Template.tdb"
    create_template(template)
    app = create_app(ServerConfig())
    with TestClient(app) as c:
        job = c.post("/api/project/create", json={"folder": str(root), "template": str(template)}).json()
        deadline = time.time() + 30
        while c.get(f"/api/jobs/{job['id']}").json()["status"] not in ("done", "error"):
            assert time.time() < deadline
            time.sleep(0.05)
        assert c.get(f"/api/jobs/{job['id']}").json()["status"] == "done"
        yield c, root


def _columns(path: Path, table: str = "DataTable") -> list[str]:
    conn = sqlite3.connect(path)
    try:
        return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    finally:
        conn.close()


def _template_labels(path: Path) -> dict[str, tuple[str, str, str]]:
    conn = sqlite3.connect(path)
    try:
        return {r[0]: (r[1], r[2], r[3]) for r in
                conn.execute("SELECT DataLabel, Type, Label, DefaultValue FROM TemplateTable")}
    finally:
        conn.close()


def test_bare_project_starts_with_nothing_to_choose(bare):
    client, _root = bare
    project = client.get("/api/project").json()
    assert [c for c in project["controls"] if c["type"] in ("Flag", "Counter")] == []
    assert client.get("/api/palette/suggest").json()["items"] == []
    assert all(project["eventColumns"][k] is None for k in
               ("speciesName", "individual", "entry", "exit", "exitFile", "startInside", "endInside", "duration"))


def test_add_species_from_scratch(bare):
    client, root = bare
    first = client.post("/api/template/species", json={"name": "タヌキ", "countSuffix": "の個数"}).json()
    assert first["added"] == {"flag": "Species1", "counter": "Species1Count"} and first["templateUpdated"] is True
    second = client.post("/api/template/species", json={"name": "Red fox", "counter": False}).json()
    assert second["added"] == {"flag": "RedFox", "counter": None}
    assert second["settings"]["palette"]["items"] == [
        {"flag": "Species1", "counter": "Species1Count", "key": "1"},
        {"flag": "RedFox", "counter": None, "key": "2"},
    ]
    # Both files got the fields, with the name people typed as the label.
    for path in (root / "Template.ddb", root / "Template.tdb"):
        labels = _template_labels(path)
        assert labels["Species1"] == ("Flag", "タヌキ", "false")
        assert labels["Species1Count"] == ("Counter", "タヌキの個数", "0")
        assert labels["RedFox"] == ("Flag", "Red fox", "false") and "RedFoxCount" not in labels
    assert {"Species1", "Species1Count", "RedFox"} <= set(_columns(root / "Template.ddb"))
    assert "Species1Count" in _columns(root / "Template.ddb", "MarkersTable")
    # The new species works: switch it on for a file.
    file_id = client.get("/api/files", params={"limit": 1}).json()["rows"][0]["id"]
    changed = client.patch("/api/files", json={"ids": [file_id], "values": {"Species1": "true", "Species1Count": "2"}})
    assert changed.status_code == 200 and changed.json()["rows"][0]["values"]["Species1Count"] == "2"


def test_add_species_names_and_keys(bare):
    client, _root = bare
    add = lambda name, **kw: client.post("/api/template/species", json={"name": name, **kw})
    assert add("   ").status_code == 422 and add("   ").json()["detail"]["error"] == "error.nameRequired"
    assert add("  シカ  ").json()["added"]["flag"] == "Species1"
    dup = add("シカ")
    assert dup.status_code == 400 and dup.json()["detail"]["error"] == "error.duplicateField"
    assert add("species1").status_code == 400  # a column name already in use, whatever the case
    assert add("Deer").json()["added"] == {"flag": "Deer", "counter": "DeerCount"}
    assert add("deer").status_code == 400
    assert add("File").status_code == 400  # a standard field has this name
    assert add("Group").json()["added"]["flag"] == "Species2"  # SQL keyword: not a column name
    assert add("3").json()["added"]["flag"] == "Species3"  # cannot start with a digit
    # Ten keys only: the eleventh species has none.
    for n in range(7):
        add(f"種{n}", counter=False)
    items = client.get("/api/project").json()["settings"]["palette"]["items"]
    assert [i["key"] for i in items] == list("1234567890") + [""]
    assert len({i["flag"] for i in items}) == 11


def test_add_species_keeps_what_is_there(client):
    before = client.get("/api/project").json()
    result = client.post("/api/template/species", json={"name": "SpeciesA"})
    assert result.status_code == 400  # the demo already has it
    added = client.post("/api/template/species", json={"name": "イノシシ"}).json()
    items = added["settings"]["palette"]["items"]
    assert items[:len(before["settings"]["palette"]["items"])] == before["settings"]["palette"]["items"]
    assert items[-1]["flag"] == added["added"]["flag"] and items[-1]["key"] not in [i["key"] for i in items[:-1]]
    assert len(added["controls"]) == len(before["controls"]) + 2


def test_add_event_columns_from_scratch(bare):
    client, root = bare
    labels = {"entry": "侵入（秒）", "speciesName": "  "}
    result = client.post("/api/template/event-columns", json={"labels": labels}).json()
    expected = {"speciesName": "SpeciesName", "individual": "Individual", "startInside": "InsideAtStart",
                "entry": "EntrySec", "duration": "StayDuration", "exitFile": "ExitFile", "exit": "ExitSec",
                "endInside": "InsideAtEnd"}
    assert result["added"] == expected and result["templateUpdated"] is True
    assert {k: result["eventColumns"][k] for k in expected} == expected
    assert set(expected.values()) <= set(result["lockedColumns"])
    for path in (root / "Template.ddb", root / "Template.tdb"):
        got = _template_labels(path)
        assert got["EntrySec"] == ("DecimalPositive", "侵入（秒）", "")  # empty until an event fills it
        assert got["SpeciesName"] == ("Note", "Species", "") and got["InsideAtStart"] == ("Flag", "Inside at start", "false")
    # Nothing is left to create: a second call adds nothing.
    again = client.post("/api/template/event-columns", json={}).json()
    assert again["added"] == {} and len(again["controls"]) == len(result["controls"])
    # An event now reaches the new columns.
    client.post("/api/template/species", json={"name": "タヌキ"})
    file_id = client.get("/api/files", params={"limit": 1}).json()["rows"][0]["id"]
    client.post("/api/events", json={"fileId": file_id, "frame": None, "inside": False, "species": "Species1"})
    values = client.get(f"/api/files/{file_id}").json()["values"]
    assert values["SpeciesName"] == "タヌキ" and values["Individual"] != "" and values["Species1"] == "true"
    other = client.get("/api/files", params={"limit": 3}).json()["rows"][1]["values"]
    assert other["EntrySec"] == "" and other["InsideAtStart"] == "false"


def test_add_event_columns_fills_only_the_gaps(client):
    before = client.get("/api/project").json()
    assert client.post("/api/template/event-columns", json={}).json()["added"] == {}  # the demo has them all
    columns = {**before["eventColumns"], "entry": None, "duration": "Gone"}
    client.put("/api/settings/eventColumns", json={"value": columns})
    result = client.post("/api/template/event-columns", json={}).json()
    # EntrySec and StayDuration exist already (now unused): the new fields get the next free names.
    assert result["added"] == {"entry": "EntrySec2", "duration": "StayDuration2"}
    assert result["eventColumns"]["exit"] == before["eventColumns"]["exit"]
    assert result["eventColumns"]["continuityGap"] == before["eventColumns"]["continuityGap"]
    assert len(result["controls"]) == len(before["controls"]) + 2


def test_adding_fields_to_a_read_only_project_is_refused(demo):
    app = create_app(ServerConfig())
    with TestClient(app) as c:
        c.post("/api/project/open", json={"path": str(demo)})
        c.put("/api/settings/eventColumns", json={"value": {}})  # nothing set: there would be work to do
        c.post("/api/project/open", json={"path": str(demo), "readOnly": True})
        before = _columns(demo), _template_labels(demo.with_suffix(".tdb"))
        assert c.post("/api/template/species", json={"name": "タヌキ"}).status_code == 400
        assert c.post("/api/template/event-columns", json={}).status_code == 400
        assert (_columns(demo), _template_labels(demo.with_suffix(".tdb"))) == before
        assert c.get("/api/project").json()["eventColumns"]["entry"] is None


def test_event_columns_created_later_receive_the_events_already_recorded(bare):
    client, _root = bare
    client.post("/api/template/species", json={"name": "タヌキ"})
    file_id = client.get("/api/files", params={"limit": 1}).json()["rows"][0]["id"]
    started = client.post("/api/events", json={"fileId": file_id, "frame": None, "inside": True, "species": "Species1"})
    assert started.status_code == 200
    client.post("/api/template/event-columns", json={})
    values = client.get(f"/api/files/{file_id}").json()["values"]
    assert values["SpeciesName"] == "タヌキ" and values["InsideAtStart"] == "true" and values["Individual"] != ""


def test_template_in_use_changes_neither_file(bare):
    client, root = bare
    ddb, tdb = root / "Template.ddb", root / "Template.tdb"
    before = _columns(ddb), _template_labels(ddb), _template_labels(tdb)
    other = sqlite3.connect(tdb)
    try:
        other.execute("BEGIN EXCLUSIVE")  # as when another program is writing the template
        refused = client.post("/api/template/species", json={"name": "タヌキ"})
        assert refused.status_code == 400 and refused.json()["error"] == "error.templateBusy"
        assert client.post("/api/template/event-columns", json={}).status_code == 400
    finally:
        other.rollback()
        other.close()
    assert (_columns(ddb), _template_labels(ddb), _template_labels(tdb)) == before
    project = client.get("/api/project").json()
    assert project["settings"].get("palette") is None and project["eventColumns"]["entry"] is None
    # Once the template is free, the same request works and takes the same first name.
    assert client.post("/api/template/species", json={"name": "タヌキ"}).json()["added"]["flag"] == "Species1"
    assert "Species1" in _template_labels(tdb) and "Species1" in _columns(ddb)


@pytest.mark.parametrize("known_to", ["Template.tdb", "Template.ddb"])
def test_failure_half_way_rolls_both_files_back(bare, known_to):
    client, root = bare
    ddb, tdb = root / "Template.ddb", root / "Template.tdb"
    conn = sqlite3.connect(root / known_to)  # one file already has the second field: it fails there
    conn.execute("INSERT INTO TemplateTable (ControlOrder, SpreadsheetOrder, Type, DefaultValue, Label, DataLabel,"
                 " Tooltip, TXTBOXWIDTH, Copyable, Visible, List, ExportToCSV)"
                 " SELECT 99, 99, 'Flag', 'false', 'x', 'Species1Count', '', '20', 'true', 'true', '', 'true'")
    conn.commit()
    conn.close()
    before = _columns(ddb), _template_labels(ddb), _template_labels(tdb)
    project = client.app.state.workspace.project
    with pytest.raises(ProjectError) as failure:
        project.add_controls([{"type": "Flag", "label": "タヌキ", "dataLabel": "Species1"},
                              {"type": "Counter", "label": "n", "dataLabel": "Species1Count"}], tdb)
    assert failure.value.key == "error.duplicateField"
    assert (_columns(ddb), _template_labels(ddb), _template_labels(tdb)) == before
    assert "Species1" not in project.by_label
    assert client.get("/api/project").status_code == 200


def test_project_still_loads_while_the_template_is_in_use(bare):
    client, root = bare
    other = sqlite3.connect(root / "Template.tdb")
    try:
        other.execute("BEGIN EXCLUSIVE")
        shown = client.get("/api/project")
        assert shown.status_code == 200 and shown.json()["templatePath"] is None
    finally:
        other.rollback()
        other.close()
    assert client.get("/api/project").json()["templatePath"] == str(root / "Template.tdb")


def test_add_event_columns_creates_the_keys_asked_for(client):
    before = client.get("/api/project").json()
    # On screen "entry" was switched to none (not saved): it is created although a field is saved for it.
    result = client.post("/api/template/event-columns", json={"keys": ["entry"]}).json()
    assert result["added"] == {"entry": "EntrySec2"}
    assert len(result["controls"]) == len(before["controls"]) + 1
    # An empty list asks for nothing, even with gaps saved.
    client.put("/api/settings/eventColumns", json={"value": {}})
    assert client.post("/api/template/event-columns", json={"keys": []}).json()["added"] == {}
    bad = client.post("/api/template/event-columns", json={"keys": ["nope"]})
    assert bad.status_code == 400 and bad.json()["detail"]["error"] == "error.unknownField"


@pytest.mark.parametrize("broken", [None, "text", [], {"items": None}, {"items": ["SpeciesA", {"key": "1"}, 3]},
                                    {"items": [{"flag": "SpeciesA", "counter": None, "key": "1"}], "single": True}])
def test_add_species_survives_a_broken_palette(client, broken):
    client.put("/api/settings/palette", json={"value": broken})
    result = client.post("/api/template/species", json={"name": "イノシシ"})
    assert result.status_code == 200
    items = result.json()["settings"]["palette"]["items"]
    assert items[-1]["flag"] == result.json()["added"]["flag"]
    assert all(isinstance(i, dict) and isinstance(i["flag"], str) for i in items)
    if isinstance(broken, dict) and broken.get("single"):
        assert items[0] == {"flag": "SpeciesA", "counter": None, "key": "1"} and items[-1]["key"] == "2"
        assert result.json()["settings"]["palette"]["single"] is True


def test_reads_from_many_threads_share_the_connection_safely(client):
    """Request threads share one connection (regression: 'bad parameter or other API misuse')."""
    import threading
    project = client.app.state.workspace.project
    first = client.get("/api/files/ids?filter=%7B%7D").json()[0]
    errors: list[BaseException] = []

    def read():
        try:
            for _ in range(300):
                project.markers(first)
                project.image_set()
                project.detections(first)
                project.detection_categories()
        except BaseException as exc:  # noqa: BLE001 - whatever the driver throws is the failure
            errors.append(exc)

    threads = [threading.Thread(target=read) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert errors == []


def test_request_arriving_after_the_project_was_closed_is_not_a_crash(client):
    project = client.app.state.workspace.project
    first = client.get("/api/files/ids?filter=%7B%7D").json()[0]
    project.close()  # as when another request closes it while this one is on its way
    late = client.get(f"/api/files/{first}")
    assert late.status_code == 409 and late.json()["error"] == "error.noProject"

