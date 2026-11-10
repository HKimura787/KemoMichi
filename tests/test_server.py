import base64
import json
import time

from pathlib import Path

import pytest
from conftest import needs_ffmpeg
from fastapi.testclient import TestClient

from kemocore.demo import make_image
from kemocore.timelapse.create import create_template, scan_media
from kemoserver.app import create_app
from kemoserver.security import ServerConfig


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
    # Test file_detail returns fileRest
    vid = client.get("/api/files/ids", params={"filter": json.dumps({"text": "VID_0001"})}).json()[0]
    detail = client.get(f"/api/files/{vid}").json()
    assert "fileRest" in detail

    # Test save capture endpoint
    # 1x1 black pixel JPEG base64
    fake_img = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
    res = client.post("/api/capture", json={"fileId": vid, "filename": "test_shot.jpg", "image": fake_img})
    assert res.status_code == 200
    data = res.json()
    assert "path" in data
    assert Path(data["path"]).exists()
    assert Path(data["path"]).read_bytes() != b""


def test_duplicate_file_api(client):
    vid = client.get("/api/files/ids", params={"filter": json.dumps({"text": "VID_0001"})}).json()[0]
    detail_before = client.get(f"/api/files/{vid}").json()
    assert detail_before["recordIndex"] == 1
    assert detail_before["recordTotal"] == 1

    res = client.post(f"/api/files/{vid}/duplicate")
    assert res.status_code == 200
    data = res.json()
    new_id = data["id"]
    assert new_id != vid

    detail_after = client.get(f"/api/files/{vid}").json()
    assert detail_after["recordIndex"] == 1
    assert detail_after["recordTotal"] == 2

    dup_detail = client.get(f"/api/files/{new_id}").json()
    assert dup_detail["recordIndex"] == 2
    assert dup_detail["recordTotal"] == 2
    assert dup_detail["values"]["File"] == detail_before["values"]["File"]

    # 404 for non-existent file
    assert client.post("/api/files/999999/duplicate").status_code == 404
