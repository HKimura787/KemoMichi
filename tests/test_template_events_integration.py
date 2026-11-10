import sqlite3
import time

from fastapi.testclient import TestClient

from kemocore.demo import make_image
from kemocore.timelapse.create import create_template
from kemoserver.app import create_app
from kemoserver.security import ServerConfig


def test_confirmed_template_works_with_numbered_events_and_all_record_listing(tmp_path):
    source = tmp_path / "source.tdb"
    create_template(source)
    root = tmp_path / "images"
    root.mkdir()
    make_image(root / "sample.jpg", None, "sample")
    original = source.read_bytes()
    app = create_app(ServerConfig(roots=[tmp_path]))
    try:
        with TestClient(app) as client:
            preview = client.get("/api/template", params={"path": str(source), "folder": str(root)}).json()
            controls = preview["controls"]
            fields = [("SpeciesA", "Flag", "false"), ("SpeciesACount", "Counter", "0"),
                      ("SpeciesName", "Note", ""), ("Individual", "Note", ""),
                      ("EntrySec", "DecimalPositive", ""), ("ExitSec", "DecimalPositive", ""),
                      ("StayDuration", "DecimalPositive", "")]
            for index, (label, kind, default) in enumerate(fields, 1):
                controls.append({"id": -index, "label": "ニホンジカ" if label == "SpeciesA" else label,
                                 "dataLabel": label, "type": kind, "defaultValue": default})
            created = client.post("/api/project/create", json={"folder": str(root), "template": str(source),
                "draft": {"name": "confirmed", "revision": preview["revision"], "controls": controls}})
            assert created.status_code == 200, created.text
            for _ in range(200):
                job = client.get(f"/api/jobs/{created.json()['id']}").json()
                if job["status"] != "running": break
                time.sleep(0.01)
            assert job["status"] == "done", job
            palette = {"items": [{"flag": "SpeciesA", "counter": "SpeciesACount", "key": "1"}], "single": False}
            assert client.put("/api/settings/palette", json={"value": palette}).status_code == 200
            mapping = {"speciesName": "SpeciesName", "individual": "Individual", "entry": "EntrySec",
                       "exit": "ExitSec", "duration": "StayDuration", "writeSpecies": True}
            assert client.put("/api/settings/eventColumns", json={"value": mapping}).status_code == 200
            first = client.post("/api/events", json={"fileId": 1, "species": "SpeciesA"}).json()["event"]
            second = client.post("/api/events", json={"fileId": 1, "species": "SpeciesA"}).json()["event"]
            assert (first["individual"], second["individual"]) == ("1", "2")
            assert client.get("/api/files/ids").json() == [1]
            all_ids = client.get("/api/files/ids", params={"records": True}).json()
            assert len(all_ids) == 2
            listed = client.get("/api/files", params={"records": True}).json()
            assert listed["total"] == 2
            assert {row["values"]["Individual"] for row in listed["rows"]} == {"1", "2"}
            assert all(row["values"]["SpeciesName"] == "ニホンジカ" for row in listed["rows"])
            filtered = client.get("/api/files/ids", params={"records": True, "filter": '{"text":"ニホンジカ"}'}).json()
            assert filtered == all_ids
            # Auto-managed event columns stay protected, including in the spreadsheet.
            blocked = client.patch("/api/files", json={"ids": all_ids, "values": {"Individual": "99"}})
            assert blocked.status_code == 400
            assert source.read_bytes() == original
            with sqlite3.connect(root / "confirmed.tdb") as conn:
                assert conn.execute("SELECT Label FROM TemplateTable WHERE DataLabel='SpeciesA'").fetchone()[0] == "ニホンジカ"
    finally:
        app.state.workspace.close()
