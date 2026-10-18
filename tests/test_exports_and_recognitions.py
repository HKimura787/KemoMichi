import json
import sqlite3
from fractions import Fraction

from conftest import needs_ffmpeg

from kemocore import media, rest
from kemocore.sidecar import Sidecar
from kemocore.timelapse.csv_export import export_csv
from kemocore.timelapse.project import TimelapseProject
from kemocore.timelapse.recognitions import import_recognitions


def test_csv_matches_timelapse_format(demo):
    project = TimelapseProject(demo)
    project.update([1], {"Note": 'say "hi", ok'})
    path = export_csv(project)
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
    assert report.images_matched == 4
    assert report.unmatched_files == ["Elsewhere\\missing.JPG"]
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
    assert video == [(30, 29.97)]
    assert project.detections(1)[0]["bbox"] == [0.098, 0.198, 0.304, 0.404]
    assert project.detections(1)[0]["category"] == "1"
    assert project.detection_categories()["detection"]["0"] == "Empty"

    # Re-importing merges by label and replaces the listed images' detections.
    import_recognitions(project, _recognition_json(tmp_path))
    assert conn.execute("SELECT COUNT(*) FROM Detections WHERE Id = 1").fetchone()[0] == 1


@needs_ffmpeg
def test_video_interval_is_exact(demo):
    project = TimelapseProject(demo)
    video_id = project.ids({"text": "VID_0001"})[0]
    interval = rest.video_interval(project, video_id, 0, 30)
    # 30 frames at 30000/1001 fps is exactly 1.001 s.
    assert interval["duration_seconds"] == "1.001"
    info = media.video_info(project.media_path(project.file(video_id)))
    assert media.frame_seconds(info, 30) == Fraction(1001, 1000)


@needs_ffmpeg
def test_interval_columns_are_written(demo):
    project = TimelapseProject(demo)
    sidecar = Sidecar(demo)
    sidecar.set(rest.SETTINGS_KEY, {"start": "StayStart", "end": "StayEnd", "duration": "StayDuration", "multi": "sum"})
    video_id = project.ids({"text": "VID_0001"})[0]
    sidecar.save_interval(rest.video_interval(project, video_id, 3, 33))
    sidecar.save_interval(rest.video_interval(project, video_id, 60, 75))
    values = rest.write_columns(project, sidecar, video_id)
    assert values["StayDuration"] == "1.5015"  # (30 + 15) frames * 1001/30000
    assert values["StayStart"] == "0.1001"
    assert project.file(video_id)["values"]["StayEnd"] == values["StayEnd"]
    assert rest.locked_columns(sidecar) == {"StayStart", "StayEnd", "StayDuration"}


def test_sequence_interval_uses_image_times(demo):
    project = TimelapseProject(demo)
    interval = rest.sequence_interval(project, 2, 1)
    assert interval["start_file_id"] == 1 and interval["duration_seconds"] == str(37 * 60 + 1)


def test_sidecar_folder_settings_inherit(demo):
    sidecar = Sidecar(demo)
    sidecar.set_folder("CamA", "guides", [{"shape": "triangle"}])
    assert sidecar.get_folder("CamA\\2026-04", "guides") == [{"shape": "triangle"}]
    assert sidecar.get_folder("CamB\\2026-04", "guides") is None
    assert sidecar.path.name == "TimelapseData.ddb.kemomichi"


def test_read_only_sidecar_creates_nothing(demo):
    sidecar = Sidecar(demo, read_only=True)
    assert sidecar.get("x") is None
    assert not sidecar.path.exists()
