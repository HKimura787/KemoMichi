from pathlib import Path

from fastapi.testclient import TestClient

from kemoserver.app import create_app
from kemoserver.security import ServerConfig


def test_browse_accepts_folders_and_both_project_file_types(demo):
    app = create_app(ServerConfig(roots=[demo.parent]))
    with TestClient(app) as client:
        folder = client.get("/api/browse", params={"path": str(demo.parent)}).json()
        assert folder["selected"] is None
        assert {file["kind"] for file in folder["files"]} == {"tdb", "ddb"}
        for file in (demo, demo.with_suffix(".tdb")):
            response = client.get("/api/browse", params={"path": str(file)})
            assert response.status_code == 200
            assert response.json()["path"] == str(demo.parent)
            assert response.json()["selected"] == {"name": file.name, "path": str(file), "kind": file.suffix[1:]}


def test_review_position_survives_reopening_without_changing_ddb(demo):
    app = create_app(ServerConfig(open_path=demo))
    before = demo.read_bytes()
    position = {"fileId": 2, "frame": 17, "filter": {"folder": "CamA"}, "view": "viewer"}
    try:
        with TestClient(app) as client:
            response = client.put("/api/review-position", json={"expectedPath": str(demo), **position})
            assert response.status_code == 200 and response.json()["saved"]
            client.post("/api/project/close")
            opened = client.post("/api/project/open", json={"path": str(demo)}).json()
            assert opened["settings"]["reviewPosition"] == position
            assert demo.read_bytes() == before
            stale = client.put("/api/review-position", json={"expectedPath": str(demo.parent / "other.ddb"), **position})
            assert stale.status_code == 409
            invalid = client.put("/api/review-position", json={"expectedPath": str(demo), **position, "frame": -1})
            assert invalid.status_code == 422
            client.post("/api/project/open", json={"path": str(demo), "readOnly": True})
            response = client.put("/api/review-position", json={"expectedPath": str(demo), **position, "frame": 29})
            assert response.json() == {"saved": False}
            assert client.get("/api/project").json()["settings"]["reviewPosition"] == position
    finally:
        app.state.workspace.close()


def test_csv_download_uses_the_ddb_name(demo):
    app = create_app(ServerConfig(open_path=demo))
    try:
        with TestClient(app) as client:
            exported = client.post("/api/export/csv", json={}).json()
            assert Path(exported["path"]) == demo.with_suffix(".csv")
            response = client.get("/api/export/csv")
            assert response.status_code == 200
            assert f'filename="{demo.stem}.csv"' in response.headers["content-disposition"]
    finally:
        app.state.workspace.close()
