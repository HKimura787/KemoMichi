"""Import a MegaDetector-format recognition JSON into a .ddb as Timelapse2 does (spec §3)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import constants as C
from .project import ProjectError, TimelapseProject, _table_exists

INFO_SQL = (
    f"CREATE TABLE {C.INFO_TABLE} (infoID INTEGER PRIMARY KEY, detector STRING, "
    "megadetector_version STRING DEFAULT 'vUnknown', detection_completion_time STRING, classifier STRING, "
    "classification_completion_time STRING, typical_detection_threshold REAL DEFAULT 0.2, "
    "conservative_detection_threshold REAL DEFAULT 0.05, typical_classification_threshold REAL DEFAULT 0.5)"
)
DETECTION_CATEGORIES_SQL = f"CREATE TABLE {C.DETECTION_CATEGORIES} (category STRING PRIMARY KEY, label STRING)"
CLASSIFICATION_CATEGORIES_SQL = (
    f"CREATE TABLE {C.CLASSIFICATION_CATEGORIES} (classification STRING PRIMARY KEY, label STRING, "
    "description STRING DEFAULT '')"
)
DETECTIONS_SQL = (
    f"CREATE TABLE {C.DETECTIONS} (detectionID INTEGER PRIMARY KEY, category STRING, conf REAL, bbox STRING, "
    f"classification STRING, classification_conf REAL, Id INTEGER, "
    f"FOREIGN KEY (Id) REFERENCES {C.DATA_TABLE}(Id) ON DELETE CASCADE)"
)
DETECTIONS_VIDEO_SQL = (
    f"CREATE TABLE {C.DETECTIONS_VIDEO} (frame_number INTEGER, frame_rate REAL, detectionID INTEGER, "
    f"FOREIGN KEY (detectionID) REFERENCES {C.DETECTIONS}(detectionID) ON DELETE CASCADE)"
)
INDEXES = (
    f"CREATE INDEX IF NOT EXISTS IndexDetectionID ON {C.DETECTIONS} (Id)",
    f"CREATE INDEX IF NOT EXISTS IndexDetectionVideoID ON {C.DETECTIONS_VIDEO} (detectionID)",
    f"CREATE INDEX IF NOT EXISTS IndexDetectionsClassificationConfidence ON {C.DETECTIONS} "
    "(classification, conf, classification_conf, Id)",
)


@dataclass
class ImportReport:
    images_matched: int = 0
    detections_stored: int = 0
    unmatched_files: list[str] = field(default_factory=list)
    skipped_video_without_rate: int = 0
    trimmed_low_confidence: int = 0

    def to_dict(self) -> dict:
        return {
            "imagesMatched": self.images_matched,
            "detectionsStored": self.detections_stored,
            "unmatchedFiles": self.unmatched_files[:50],
            "unmatchedCount": len(self.unmatched_files),
            "skippedVideoWithoutRate": self.skipped_video_without_rate,
            "trimmedLowConfidence": self.trimmed_low_confidence,
        }


def _r3(value: float) -> float:
    return round(float(value), 3)


def _adjust_bbox(bbox) -> str:
    """Timelapse enlarges stored boxes slightly and rounds them (spec §3.2)."""
    if not isinstance(bbox, list) or len(bbox) != 4:
        return ""
    x, y, w, h = (float(v) for v in bbox)
    x, y, w, h = max(0.0, x - 0.002), max(0.0, y - 0.002), w + 0.004, h + 0.004
    return ", ".join(_fmt(_r3(v)) for v in (x, y, w, h))


def _fmt(value: float) -> str:
    text = repr(value)
    return text[:-2] if text.endswith(".0") else text


def import_recognitions(project: TimelapseProject, json_path: Path) -> ImportReport:
    """Replace or merge recognitions for the images listed in the JSON."""
    project._ensure_writable()
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    info = data.get("info") or {}
    det_meta = info.get("detector_metadata") or {}
    cls_meta = info.get("classifier_metadata") or {}
    conservative = float(det_meta.get("conservative_detection_threshold", 0.05))
    typical_cls = float(cls_meta.get("typical_classification_threshold", 0.5))
    det_floor = max(0.03, conservative / 2.5)
    cls_floor = max(0.03, typical_cls / 2.5)

    det_cats = {str(k): str(v) for k, v in (data.get("detection_categories") or {}).items()}
    cls_cats = {str(k): str(v) for k, v in (data.get("classification_categories") or {}).items()}
    descriptions = {str(k): str(v) for k, v in (data.get("classification_category_descriptions") or {}).items()}
    unknown_n = 0
    for key, label in list(cls_cats.items()):
        if not label.strip():
            unknown_n += 1
            cls_cats[key] = "unknownClassification" + ("" if unknown_n == 1 else str(unknown_n))
            descriptions.pop(key, None)

    report = ImportReport()
    conn = project.conn
    with project.lock:
        project._backup_if_needed()
        index = {}
        for row in conn.execute(f"SELECT Id, File, RelativePath FROM {C.DATA_TABLE}"):
            key = ((row["RelativePath"] or "").lower(), (row["File"] or "").lower())
            index.setdefault(key, []).append(row["Id"])

        with conn:
            existing = _table_exists(conn, C.DETECTIONS)
            if existing:
                det_map = _merge_categories(conn, C.DETECTION_CATEGORIES, "category", det_cats)
                cls_map = _merge_categories(conn, C.CLASSIFICATION_CATEGORIES, "classification", cls_cats,
                                            descriptions)
            else:
                for sql in (INFO_SQL, DETECTION_CATEGORIES_SQL, CLASSIFICATION_CATEGORIES_SQL, DETECTIONS_SQL,
                            DETECTIONS_VIDEO_SQL):
                    conn.execute(sql)
                if "0" not in det_cats:
                    det_cats = {"0": "Empty", **det_cats}
                for k, v in det_cats.items():
                    conn.execute(f"INSERT INTO {C.DETECTION_CATEGORIES} VALUES (?,?)", (k, v))
                for k, v in cls_cats.items():
                    conn.execute(f"INSERT INTO {C.CLASSIFICATION_CATEGORIES} VALUES (?,?,?)",
                                 (k, v, descriptions.get(k, "")))
                det_map = {k: k for k in det_cats}
                cls_map = {k: k for k in cls_cats}
            for sql in INDEXES:
                conn.execute(sql)
            _write_info(conn, info, det_meta, cls_meta, replace=not existing)

            next_id = (conn.execute(f"SELECT MAX(detectionID) FROM {C.DETECTIONS}").fetchone()[0] or 0) + 1
            for image in data.get("images") or []:
                file_text = str(image.get("file", "")).replace("/", "\\")
                rel, _, name = file_text.rpartition("\\")
                ids = index.get((rel.lower(), name.lower()))
                if not ids:
                    report.unmatched_files.append(file_text)
                    continue
                report.images_matched += 1
                is_image = name.lower().endswith((".jpg", ".jpeg"))
                frame_rate = float(image.get("frame_rate") or 0)
                detections = image.get("detections")
                for file_id in ids:
                    conn.execute(f"DELETE FROM {C.DETECTIONS} WHERE Id = ?", (file_id,))
                if detections is None:
                    continue
                kept = []
                for det in detections:
                    if float(det.get("conf", 0)) < det_floor:
                        report.trimmed_low_confidence += 1
                        continue
                    kept.append(det)
                kept.sort(key=lambda d: int(d.get("frame_number", 0) or 0))
                stored_any = False
                for det in kept:
                    best = None
                    for pair in det.get("classifications") or []:
                        if len(pair) == 2 and float(pair[1]) >= cls_floor:
                            if best is None or float(pair[1]) > float(best[1]):
                                best = pair
                    category = det_map.get(str(det.get("category")), str(det.get("category")))
                    classification = cls_map.get(str(best[0]), str(best[0])) if best else None
                    row = (category, _r3(det.get("conf", 0)), _adjust_bbox(det.get("bbox")), classification,
                           _r3(best[1]) if best else None)
                    if is_image:
                        for file_id in ids:
                            conn.execute(f"INSERT INTO {C.DETECTIONS} VALUES (?,?,?,?,?,?,?)",
                                         (next_id, *row, file_id))
                            next_id += 1
                        stored_any = True
                        report.detections_stored += 1
                    else:
                        frame = int(det.get("frame_number", 0) or 0)
                        if frame >= 0 and frame_rate > 0:
                            for file_id in ids:
                                conn.execute(f"INSERT INTO {C.DETECTIONS} VALUES (?,?,?,?,?,?,?)",
                                             (next_id, *row, file_id))
                                conn.execute(f"INSERT INTO {C.DETECTIONS_VIDEO} VALUES (?,?,?)",
                                             (frame, frame_rate, next_id))
                                next_id += 1
                            stored_any = True
                            report.detections_stored += 1
                        else:
                            report.skipped_video_without_rate += 1
                            next_id += 1
                # A processed file with nothing left gets one "category 0" row as a processed mark.
                # Videos whose detections were all dropped for lacking a frame rate get none.
                if not stored_any and (is_image or not kept):
                    for file_id in ids:
                        conn.execute(f"INSERT INTO {C.DETECTIONS} VALUES (?,?,?,?,?,?,?)",
                                     (next_id, "0", 0, "", None, None, file_id))
                        next_id += 1
    project.reload_template()
    return report


def _merge_categories(conn, table: str, key_col: str, incoming: dict[str, str],
                      descriptions: dict[str, str] | None = None) -> dict[str, str]:
    """Match incoming categories to existing ones by label; returns incoming number -> stored number."""
    existing = {str(r[0]): r[1] for r in conn.execute(f"SELECT {key_col}, label FROM {table}")}
    by_label = {label: number for number, label in existing.items()}
    mapping = {}
    next_number = max([int(n) for n in existing if n.isdigit()] or [0]) + 1
    for number, label in incoming.items():
        if label in by_label:
            mapping[number] = by_label[label]
            continue
        target = number if number not in existing else str(next_number)
        if target == str(next_number):
            next_number += 1
        if target in existing and existing[target] != label:
            raise ProjectError("error.incompatibleCategories")
        if descriptions is not None:
            conn.execute(f"INSERT INTO {table} VALUES (?,?,?)", (target, label, descriptions.get(number, "")))
        else:
            conn.execute(f"INSERT INTO {table} VALUES (?,?)", (target, label))
        existing[target] = label
        by_label[label] = target
        mapping[number] = target
    return mapping


def _write_info(conn, info: dict, det_meta: dict, cls_meta: dict, replace: bool) -> None:
    values = {
        "detector": info.get("detector", ""),
        "megadetector_version": det_meta.get("megadetector_version", "vUnknown"),
        "detection_completion_time": info.get("detection_completion_time", ""),
        "classifier": info.get("classifier", ""),
        "classification_completion_time": info.get("classification_completion_time", ""),
        "typical_detection_threshold": float(det_meta.get("typical_detection_threshold", 0.2)),
        "conservative_detection_threshold": float(det_meta.get("conservative_detection_threshold", 0.05)),
        "typical_classification_threshold": float(cls_meta.get("typical_classification_threshold", 0.5)),
    }
    row = conn.execute(f"SELECT * FROM {C.INFO_TABLE} WHERE infoID = 1").fetchone()
    if row is None or replace:
        conn.execute(f"DELETE FROM {C.INFO_TABLE}")
        conn.execute(f"INSERT INTO {C.INFO_TABLE} (infoID, {', '.join(values)}) VALUES (1, {', '.join('?' for _ in values)})",
                     list(values.values()))
        return
    # Merge: thresholds take the minimum (spec §3.3).
    for key in ("typical_detection_threshold", "conservative_detection_threshold", "typical_classification_threshold"):
        old = row[key]
        values[key] = min(values[key], old) if old is not None else values[key]
    conn.execute(f"UPDATE {C.INFO_TABLE} SET {', '.join(f'{k} = ?' for k in values)} WHERE infoID = 1",
                 list(values.values()))
