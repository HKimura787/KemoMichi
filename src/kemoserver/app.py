"""HTTP API for the KemoMichi web UI."""

from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from kemocore import __version__, events, media
from kemocore.demo import create_demo_project
from kemocore.timelapse import constants as C
from kemocore.timelapse.create import create_data_file
from kemocore.timelapse.csv_export import export_csv
from kemocore.timelapse.project import ProjectError
from kemocore.timelapse.recognitions import import_recognitions
from kemocore.timelapse.template import ValueError_, make_data_label
from kemocore.timelapse.template_edit import (
    project_name, read_template, suggest_name, validate_controls, write_template_copy,
)

from .media_response import cached_file_response
from .security import BasicAuthMiddleware, ServerConfig
from .template_models import TemplateDraft
from .workspace import Jobs, Workspace

STATIC_DIR = Path(__file__).parent / "static"


def create_app(config: ServerConfig) -> FastAPI:
    app = FastAPI(title="KemoMichi", version=__version__)
    ws = Workspace()
    jobs = Jobs()
    app.state.workspace = ws
    app.state.jobs = jobs
    app.state.config = config

    @app.exception_handler(ProjectError)
    async def project_error(_request: Request, exc: ProjectError):
        return JSONResponse(status_code=400, content={"error": exc.key, "params": exc.params})

    @app.exception_handler(ValueError_)
    async def value_error(_request: Request, exc: ValueError_):
        return JSONResponse(status_code=422, content={"error": exc.key, "params": exc.params})

    def project():
        if ws.project is None:
            raise HTTPException(409, detail={"error": "error.noProject"})
        return ws.project

    def checked_path(text: str) -> Path:
        path = Path(text).expanduser()
        if not path.is_absolute() or not config.allowed(path):
            raise HTTPException(403, detail={"error": "error.pathNotAllowed", "params": {"path": text}})
        return path.resolve()

    def file_or_404(file_id: int) -> dict:
        row = project().file(file_id)
        if row is None:
            raise HTTPException(404, detail={"error": "error.fileNotFound"})
        return row

    # ---- app and browsing ------------------------------------------------------------------

    @app.get("/api/info")
    def info():
        return {
            "version": __version__,
            "serverMode": config.server_mode,
            "host": config.host,
            "startFolders": config.start_folders(),
            "ffmpeg": media.has_ffmpeg(),
            "projectOpen": ws.project is not None,
        }

    @app.get("/api/browse")
    def browse(path: str):
        folder = checked_path(path)
        selected = None
        if folder.is_file() and folder.suffix.lower() in (".ddb", ".tdb", ".json"):
            selected = {"name": folder.name, "path": str(folder), "kind": folder.suffix.lower()[1:]}
            folder = folder.parent
        if not folder.is_dir():
            raise HTTPException(404, detail={"error": "error.notFound", "params": {"path": path}})
        dirs, files = [], []
        try:
            entries = sorted(folder.iterdir(), key=lambda p: p.name.lower())
        except PermissionError:
            raise HTTPException(403, detail={"error": "error.permission", "params": {"path": path}})
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir():
                    dirs.append({"name": entry.name, "path": str(entry)})
                elif entry.suffix.lower() in (".ddb", ".tdb", ".json"):
                    files.append({"name": entry.name, "path": str(entry), "kind": entry.suffix.lower()[1:]})
            except OSError:
                continue
        parent = folder.parent if folder.parent != folder and config.allowed(folder.parent) else None
        return {"path": str(folder), "parent": str(parent) if parent else None, "dirs": dirs, "files": files,
                "selected": selected}

    # ---- project -----------------------------------------------------------------------------

    def project_payload():
        p = project()
        payload = p.info()
        payload["settings"] = ws.sidecar.all_settings()
        payload["lockedColumns"] = sorted(events.locked_columns(ws.sidecar))
        payload["eventColumns"] = events.column_settings(ws.sidecar)
        payload["duplicates"] = {str(k): v for k, v in ws.sidecar.all_duplicates().items()}
        payload["categories"] = p.detection_categories()
        payload["folders"] = p.folders()
        template = p.find_template()
        payload["templatePath"] = str(template) if template else None
        payload["canUndo"] = bool(p.undo_stack)
        payload["canRedo"] = bool(p.redo_stack)
        return payload

    @app.get("/api/project")
    def get_project():
        return project_payload()

    @app.post("/api/project/open")
    def open_project(path: str = Body(..., embed=True), readOnly: bool = Body(False, embed=True)):
        target = checked_path(path)
        if target.suffix.lower() == ".tdb":
            raise HTTPException(400, detail={"error": "error.openTemplate"})
        ws.open(target, read_only=readOnly)
        return project_payload()

    @app.post("/api/project/close")
    def close_project():
        ws.close()
        return {"ok": True}

    @app.get("/api/template")
    def get_template(path: str, folder: str):
        source = checked_path(path)
        root = checked_path(folder)
        if not root.is_dir():
            raise HTTPException(404, detail={"error": "error.notFound", "params": {"path": folder}})
        document = read_template(source)
        return {"path": str(source), "revision": document.revision,
                "controls": [control.to_dict() for control in document.controls],
                "suggestedName": suggest_name(root, source.stem)}

    def template_plan(folder: str, template: str, draft: TemplateDraft):
        root, source = checked_path(folder), checked_path(template)
        if not root.is_dir():
            raise HTTPException(404, detail={"error": "error.notFound", "params": {"path": folder}})
        document = read_template(source)
        if document.revision != draft.revision:
            raise HTTPException(409, detail={"error": "error.templateChanged"})
        controls = validate_controls([control.model_dump() for control in draft.controls], document)
        name = project_name(draft.name)
        local_template, ddb = root / f"{name}.tdb", root / f"{name}.ddb"
        if ddb.exists():
            raise HTTPException(409, detail={"error": "error.ddbExists", "params": {"path": str(ddb)}})
        if local_template.exists():
            raise HTTPException(409, detail={"error": "error.templateExists", "params": {"path": str(local_template)}})
        return source, local_template, ddb, controls

    @app.post("/api/template/validate")
    def validate_template(folder: str = Body(...), template: str = Body(...), draft: TemplateDraft = Body(...)):
        _source, local_template, ddb, controls = template_plan(folder, template, draft)
        return {"name": ddb.stem, "revision": draft.revision,
                "controls": [control.to_dict() for control in controls],
                "templatePath": str(local_template), "ddbPath": str(ddb)}

    @app.post("/api/project/create")
    def create_project(folder: str = Body(..., embed=True), template: str | None = Body(None, embed=True),
                       demo: bool = Body(False, embed=True), draft: TemplateDraft | None = Body(None)):
        root = checked_path(folder)
        if demo:
            def work(progress):
                ddb = create_demo_project(root)
                ws.open(ddb)
                return {"path": str(ddb)}
            return jobs.start("create", work).to_dict()
        if not template:
            raise HTTPException(400, detail={"error": "error.templateRequired"})
        if draft is not None:
            source, local_template, ddb, controls = template_plan(folder, template, draft)

            def reviewed_work(progress):
                # Serialize project creations and the final workspace switch in this server.
                with ws.lock:
                    wrote_template = wrote_ddb = False
                    try:
                        write_template_copy(source, local_template, controls, draft.revision)
                        wrote_template = True
                        count = create_data_file(ddb, local_template, progress)
                        wrote_ddb = True
                        ws.open(ddb)
                        return {"path": str(ddb), "files": count}
                    except Exception:
                        if wrote_ddb:
                            ddb.unlink(missing_ok=True)
                        if wrote_template:
                            local_template.unlink(missing_ok=True)
                        raise
            return jobs.start("create", reviewed_work).to_dict()
        template_path = checked_path(template)
        ddb = root / template_path.with_suffix(".ddb").name
        if ddb.exists():
            raise HTTPException(409, detail={"error": "error.ddbExists", "params": {"path": str(ddb)}})

        def work(progress):
            local_template = template_path
            if template_path.parent != root:
                local_template = root / template_path.name
                if not local_template.exists():
                    shutil.copy2(template_path, local_template)
            count = create_data_file(ddb, local_template, progress)
            ws.open(ddb)
            return {"path": str(ddb), "files": count}
        return jobs.start("create", work).to_dict()

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, detail={"error": "error.notFound"})
        return job.to_dict()

    # ---- files ---------------------------------------------------------------------------

    def parse_filter(text: str | None) -> dict:
        if not text:
            return {}
        try:
            value = json.loads(text)
        except ValueError:
            raise HTTPException(400, detail={"error": "error.badFilter"})
        return value if isinstance(value, dict) else {}

    @app.get("/api/folders")
    def folders():
        return project().folders()

    def list_filter(text: str | None) -> dict:
        """The UI's filter, without the rows KemoMichi duplicated for events: one stop per file."""
        flt = parse_filter(text)
        if not flt.get("ids"):
            flt["excludeIds"] = list(ws.sidecar.all_duplicates())
        return flt

    @app.get("/api/files")
    def files(filter: str | None = None, offset: int = 0, limit: int = 200):
        flt = list_filter(filter)
        p = project()
        return {"total": p.count(flt), "offset": offset, "rows": p.files(flt, offset, min(limit, 2000))}

    @app.get("/api/files/ids")
    def file_ids(filter: str | None = None):
        return project().ids(list_filter(filter))

    @app.get("/api/files/{file_id}")
    def file_detail(file_id: int):
        p = project()
        row = file_or_404(file_id)
        row["detections"] = p.detections(file_id)
        row["markers"] = p.markers(file_id)
        row["fileRest"] = ws.sidecar.file_rest(file_id)
        same = p.same_file_ids(file_id)
        row["events"] = [events.describe(p, e) for e in ws.sidecar.events_touching(same[:1])]
        row["sameFileRows"] = same
        row["duplicateOf"] = ws.sidecar.all_duplicates().get(file_id)
        row["kind"] = "video" if media.is_video(p.media_path(row)) else "image"
        row["exists"] = p.media_path(row).exists()
        rec_info = p.file_records_info(file_id)
        row["recordIndex"] = rec_info["index"]
        row["recordTotal"] = rec_info["total"]
        return row

    @app.post("/api/files/{file_id}/duplicate")
    def duplicate_file(file_id: int):
        p = project()
        file_or_404(file_id)
        new_id = p.duplicate(file_id)
        return {
            "id": new_id,
            "row": p.file(new_id),
            "total": p.count({}),
        }

    @app.patch("/api/files")
    def update_files(ids: list[int] = Body(...), values: dict = Body(...)):
        p = project()
        locked = events.locked_columns(ws.sidecar) & set(values)
        if locked:
            raise HTTPException(400, detail={"error": "error.lockedField", "params": {"field": sorted(locked)[0]}})
        batch = p.update(ids, values)
        changed = sorted({c.file_id for c in batch.changes})
        return {"changed": len(batch.changes), "rows": [p.file(i) for i in changed[:500]],
                "canUndo": bool(p.undo_stack), "canRedo": bool(p.redo_stack)}

    def history(step):
        p = project()
        batch = step()
        ids = sorted({c.file_id for c in batch.changes}) if batch else []
        return {"fileIds": ids, "rows": [p.file(i) for i in ids[:500]],
                "canUndo": bool(p.undo_stack), "canRedo": bool(p.redo_stack)}

    @app.post("/api/undo")
    def undo():
        return history(project().undo)

    @app.post("/api/redo")
    def redo():
        return history(project().redo)

    @app.put("/api/files/{file_id}/markers")
    def put_markers(file_id: int, dataLabel: str = Body(...), points: list[list[float]] = Body(...)):
        project().set_markers(file_id, dataLabel, points)
        return {"markers": project().markers(file_id)}

    # ---- media ---------------------------------------------------------------------------

    def media_file(file_id: int) -> Path:
        path = project().media_path(file_or_404(file_id))
        if not path.exists():
            raise HTTPException(404, detail={"error": "error.mediaMissing", "params": {"path": str(path)}})
        return path

    cache_headers = {"Cache-Control": "private, max-age=3600"}

    @app.get("/api/media/{file_id}/thumb")
    def thumb(file_id: int):
        path = media_file(file_id)
        if media.is_video(path):
            return cached_file_response(lambda: media.video_thumbnail(path), media_type="image/jpeg",
                                        headers=cache_headers)
        return cached_file_response(lambda: media.image_rendition(path, media.THUMB_SIZE),
                                    media_type="image/jpeg", headers=cache_headers)

    @app.get("/api/media/{file_id}/preview")
    def preview(file_id: int):
        path = media_file(file_id)
        if media.is_video(path):
            return thumb(file_id)
        return cached_file_response(lambda: media.image_rendition(path, media.PREVIEW_SIZE),
                                    media_type="image/jpeg", headers=cache_headers)

    @app.get("/api/media/{file_id}/original")
    def original(file_id: int):
        path = media_file(file_id)
        return FileResponse(path, headers=cache_headers)

    @app.get("/api/media/{file_id}/video")
    def video(file_id: int, format: str = "mp4"):
        path = media_file(file_id)
        container = "webm" if format == "webm" else "mp4"
        return cached_file_response(lambda: media.playable_video(path, container), media_type=f"video/{container}",
                                    headers=cache_headers, missing_status=415)

    @app.get("/api/media/{file_id}/video-info")
    def video_info(file_id: int):
        info = dict(media.video_info(media_file(file_id)))
        if info.get("available"):
            from fractions import Fraction
            tb = Fraction(info["timeBase"])
            info["frameTimes"] = [float(t * tb) for t in info.pop("frameTicks")]
        return info

    # ---- settings ------------------------------------------------------------------------

    @app.put("/api/review-position")
    def save_review_position(expectedPath: str = Body(...), fileId: int = Body(..., ge=1),
                             frame: int = Body(0, ge=0), filter: dict | None = Body(None),
                             view: str = Body("viewer")):
        p = project()
        if str(p.path) != expectedPath:
            raise HTTPException(409, detail={"error": "error.projectChanged"})
        if p.file(fileId) is None:
            raise HTTPException(404, detail={"error": "error.fileNotFound"})
        if view not in ("viewer", "grid", "table"):
            raise HTTPException(422, detail={"error": "error.badSetting"})
        if p.read_only:
            return {"saved": False}
        ws.sidecar.set("reviewPosition", {"fileId": fileId, "frame": frame, "filter": filter or {}, "view": view})
        return {"saved": True}

    @app.put("/api/settings/{key}")
    def put_setting(key: str, value=Body(..., embed=True)):
        ws.sidecar.set(key, value)
        if key in (events.SETTINGS_KEY, "palette") and not project().read_only:
            events.resync_all(project(), ws.sidecar)
        return {"settings": ws.sidecar.all_settings(), "lockedColumns": sorted(events.locked_columns(ws.sidecar))}

    @app.get("/api/folder-settings")
    def get_folder_settings(folder: str = ""):
        return {key: ws.sidecar.get_folder(folder, key) for key in ("guides", "color")}

    @app.put("/api/folder-settings")
    def put_folder_settings(folder: str = Body(...), key: str = Body(...), value=Body(None)):
        if key not in ("guides", "color"):
            raise HTTPException(400, detail={"error": "error.badSetting"})
        ws.sidecar.set_folder(folder, key, value)
        return {key: ws.sidecar.get_folder(folder, key)}

    @app.get("/api/palette/suggest")
    def palette_suggest():
        p = project()
        counters = [c for c in p.controls if c.type == C.COUNTER]
        items = []
        locked = events.locked_columns(ws.sidecar)
        flags = [c for c in p.controls if c.type == C.FLAG and c.visible and c.data_label not in locked]
        for i, flag in enumerate(flags):
            match = None
            names = {flag.data_label.lower() + s for s in ("count", "_count", "num", "number", "cnt", "n")}
            for counter in counters:
                if counter.data_label.lower() in names:
                    match = counter.data_label
                    break
            items.append({"flag": flag.data_label, "counter": match, "key": str(i + 1) if i < 9 else ""})
        return {"items": items, "single": False}

    @app.post("/api/template/species-counters")
    def species_counters(flags: list[str] = Body(...), labelSuffix: str = Body(" count")):
        p = project()
        taken = set(p.by_label)
        new = []
        for flag in flags:
            control = p.by_label.get(flag)
            if control is None or control.type != C.FLAG:
                raise HTTPException(400, detail={"error": "error.unknownField", "params": {"field": flag}})
            data_label = make_data_label(f"{flag}Count", taken)
            taken.add(data_label)
            new.append({"type": C.COUNTER, "label": f"{control.label}{labelSuffix}", "dataLabel": data_label,
                        "flag": flag})
        template = p.find_template()
        p.add_controls(new, template)
        palette = ws.sidecar.get("palette") or palette_suggest()
        by_flag = {n["flag"]: n["dataLabel"] for n in new}
        for item in palette.get("items", []):
            if item["flag"] in by_flag:
                item["counter"] = by_flag[item["flag"]]
        ws.sidecar.set("palette", palette)
        result = project_payload()
        result["templateUpdated"] = template is not None
        return result

    # ---- recognitions and export ---------------------------------------------------------

    @app.post("/api/recognitions/import")
    def recognitions(path: str = Body(..., embed=True)):
        report = import_recognitions(project(), checked_path(path))
        return {"report": report.to_dict(), "categories": project().detection_categories()}

    @app.post("/api/export/csv")
    def export(target: str | None = Body(None, embed=True)):
        out = export_csv(project(), checked_path(target) if target else None, sidecar=ws.sidecar)
        return {"path": str(out)}

    @app.get("/api/export/csv")
    def download_csv():
        out = export_csv(project(), sidecar=ws.sidecar)
        return FileResponse(out, media_type="text/csv", filename=out.name)

    @app.post("/api/capture")
    def capture(data: dict = Body(...)):
        p = project()
        captures_dir = p.root / "captures"
        captures_dir.mkdir(parents=True, exist_ok=True)
        filename = data.get("filename") or "capture.jpg"
        safe_name = Path(filename).name
        if not safe_name.lower().endswith((".jpg", ".jpeg", ".png")):
            safe_name += ".jpg"
        target = captures_dir / safe_name
        stem = target.stem
        suffix = target.suffix
        counter = 1
        while target.exists():
            target = captures_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        raw_b64 = data.get("image", "")
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        image_bytes = base64.b64decode(raw_b64)
        target.write_bytes(image_bytes)
        return {"path": str(target), "filename": target.name, "relative": f"captures/{target.name}"}

    # ---- REST events ---------------------------------------------------------------------

    def event_result(event: dict | None, file_ids: list[int], warning: str | None = None):
        p = project()
        changed = set()
        for fid in file_ids:
            if p.file(fid) is not None:
                changed.update(p.same_file_ids(fid))
        return {
            "event": events.describe(p, event) if event and ws.sidecar.event(event["id"]) else event,
            "open": [events.describe(p, e) for e in ws.sidecar.open_events()],
            "rows": [p.file(i) for i in sorted(changed) if p.file(i) is not None],
            "duplicates": {str(k): v for k, v in ws.sidecar.all_duplicates().items()},
            "warning": warning,
        }

    @app.get("/api/events")
    def list_events(open: bool = False):
        p = project()
        found = ws.sidecar.open_events() if open else ws.sidecar.events()
        return [events.describe(p, e) for e in found]

    @app.post("/api/events")
    def start_event(fileId: int = Body(...), frame: int | None = Body(None), inside: bool = Body(False),
                    species: str = Body(""), individual: str = Body("")):
        event = events.start_event(project(), ws.sidecar, fileId, frame, inside, species, individual)
        return event_result(event, [event["start_file_id"]])

    @app.post("/api/events/{event_id}/end")
    def end_event(event_id: int, fileId: int = Body(...), frame: int | None = Body(None),
                  inside: bool = Body(False)):
        existing = ws.sidecar.event(event_id)
        if existing is None:
            raise HTTPException(404, detail={"error": "error.notFound"})
        settings = events.column_settings(ws.sidecar)
        warning = events.continuity_warning(project(), existing["start_file_id"], fileId, settings["continuityGap"])
        event = events.end_event(project(), ws.sidecar, event_id, fileId, frame, inside)
        return event_result(event, [event["start_file_id"]], warning)

    @app.put("/api/events/{event_id}")
    def change_event(event_id: int, changes: dict = Body(...)):
        if ws.sidecar.event(event_id) is None:
            raise HTTPException(404, detail={"error": "error.notFound"})
        before = ws.sidecar.event(event_id)
        event = events.update_event(project(), ws.sidecar, event_id, changes)
        return event_result(event, [before["start_file_id"], event["start_file_id"]])

    @app.delete("/api/events/{event_id}")
    def remove_event(event_id: int):
        removed = events.delete_event(project(), ws.sidecar, event_id)
        if removed is None:
            raise HTTPException(404, detail={"error": "error.notFound"})
        return event_result(None, [removed["start_file_id"]])

    @app.post("/api/export/events")
    def export_events():
        return {"path": str(events.export_events_csv(project(), ws.sidecar))}

    # ---- web UI --------------------------------------------------------------------------

    if (STATIC_DIR / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            candidate = STATIC_DIR / path
            if path and candidate.is_file() and STATIC_DIR in candidate.resolve().parents:
                return FileResponse(candidate)
            return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})

    if config.open_path:
        target = config.open_path
        if target.is_dir():
            candidates = sorted(target.glob("*.ddb"))
            target = candidates[0] if candidates else None
        if target is not None:
            ws.open(target)

    if config.password:
        app.add_middleware(BasicAuthMiddleware, password=config.password)
    return app
