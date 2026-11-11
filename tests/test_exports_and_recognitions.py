import json
import sqlite3

from conftest import needs_ffmpeg

from kemocore import media
from kemocore.sidecar import Sidecar
from kemocore.timelapse.csv_export import export_csv
from kemocore.timelapse.project import TimelapseProject
from kemocore.timelapse.recognitions import import_recognitions


def test_csv_matches_timelapse_format(demo):
    project = TimelapseProject(demo)
    project.update([1], {"Note": 'say "hi", ok'})
    path = export_csv(project)
    assert path == demo.with_suffix(".csv")
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    lines = text.split("\r\n")
    assert lines[0].startswith("RootFolder,File,RelativePath,DateTime,")
    assert "DeleteFlag" not in lines[0]  # ExportToCSV is false for DeleteFlag
    first = lines[1]
    assert first.startswith("project,IMG_0001.JPG,CamA\\2026-04, 2026-04-01 05:30:00,")
    assert '"say ""hi"", ok"' in first
    assert text.endswith("\r\n")


def _recognition_json(tmp_path):
    data = {
        "info": {"format_version": "1.4", "detector": "md", "detector_metadata": {
            "megadetector_version": "v5a", "typical_detection_threshold": 0.2,
            "conservative_detection_threshold": 0.05}},
        "detection_categories": {"1": "animal", "2": "person"},
        "classification_categories": {"0": "SpeciesA", "1": ""},
        "images": [
            {"file": "CamA/2026-04/IMG_0001.JPG", "detections": [
                {"category": "1", "conf": 0.91234, "bbox": [0.1, 0.2, 0.3, 0.4],
                 "classifications": [["0", 0.8], ["1", 0.1]]},
                {"category": "2", "conf": 0.01, "bbox": [0, 0, 0.1, 0.1]}]},
            {"file": "CamA/2026-04/IMG_0002.JPG", "detections": []},
            {"file": "CamA/2026-04/IMG_0003.JPG", "detections": None},
            {"file": "CamA/2026-04/VID_0001.MP4", "frame_rate": 29.97, "detections": [
                {"category": "1", "conf": 0.7, "bbox": [0, 0.001, 0.5, 0.5], "frame_number": 30}]},
            {"file": "Elsewhere/missing.JPG", "detections": []},
        ],
    }
    path = tmp_path / "recognitions.json"
    path.write_text(json.dumps(data))
    return path


def test_recognitions_stored_like_timelapse(demo, tmp_path):
    project = TimelapseProject(demo)
    report = import_recognitions(project, _recognition_json(tmp_path))
    has_video = bool(project.ids({"text": "VID_0001"}))  # the demo has videos only when ffmpeg is installed
    assert report.images_matched == (4 if has_video else 3)
    assert report.unmatched_files[-1] == "Elsewhere\\missing.JPG"
    assert report.trimmed_low_confidence == 1
    conn = sqlite3.connect(demo)
    # STRING is not a real SQLite type, so numeric category keys are stored as integers (as in Timelapse).
    cats = dict(conn.execute("SELECT category, label FROM DetectionCategories"))
    assert cats[0] == "Empty" and cats[1] == "animal"
    assert dict(conn.execute("SELECT classification, label FROM ClassificationCategories"))[1] == "unknownClassification"
    rows = conn.execute("SELECT category, conf, bbox, classification, classification_conf, Id FROM Detections "
                        "ORDER BY detectionID").fetchall()
    assert rows[0] == (1, 0.912, "0.098, 0.198, 0.304, 0.404", 0, 0.8, 1)
    # Processed with nothing left: one category-0 placeholder. Null detections: nothing.
    assert (0, 0.0, "", None, None, 2) in rows
    assert not [r for r in rows if r[5] == 3]
    video = conn.execute("SELECT frame_number, frame_rate FROM DetectionsVideo").fetchall()
    assert video == ([(30, 29.97)] if has_video else [])
    assert project.detections(1)[0]["bbox"] == [0.098, 0.198, 0.304, 0.404]
    assert project.detections(1)[0]["category"] == "1"
    assert project.detection_categories()["detection"]["0"] == "Empty"

    # Re-importing merges by label and replaces the listed images' detections.
    import_recognitions(project, _recognition_json(tmp_path))
    assert conn.execute("SELECT COUNT(*) FROM Detections WHERE Id = 1").fetchone()[0] == 1


def test_sidecar_folder_settings_inherit(demo):
    sidecar = Sidecar(demo)
    sidecar.set_folder("CamA", "guides", [{"shape": "triangle"}])
    assert sidecar.get_folder("CamA\\2026-04", "guides") == [{"shape": "triangle"}]
    assert sidecar.get_folder("CamB\\2026-04", "guides") is None
    assert sidecar.path.name == f"{demo.name}.kemomichi"


def test_read_only_sidecar_creates_nothing(demo):
    demo.with_name(demo.name + ".kemomichi").unlink()
    sidecar = Sidecar(demo, read_only=True)
    assert sidecar.get("x") is None
    assert not sidecar.path.exists()


@needs_ffmpeg
def test_playback_proxies_keep_every_frame(demo):
    project = TimelapseProject(demo)
    avi = project.media_path(project.file(project.ids({"text": "VID_0002"})[0]))
    source = media.video_info(avi)["frameTicks"]
    for container in ("mp4", "webm"):
        proxy = media.playable_video(avi, container)
        assert proxy is not None and proxy != avi
        assert len(media.video_info(proxy)["frameTicks"]) == len(source)
