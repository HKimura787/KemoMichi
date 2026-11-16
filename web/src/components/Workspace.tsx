import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, type EventResult } from "../api";
import { useI18n } from "../i18n";
import type { ColorAdjust, Detection, FileDetail, Filter, Guide, Info, Palette, Project, ReviewPosition, RestEvent, Row, ShapeKind, VideoInfo } from "../types";
import { useToast } from "../ui";
import { DELETED, ENTERED, type TreeData } from "../tree";
import { DataPanel, isTrue, speciesChange } from "./DataPanel";
import { FileTree } from "./FileTree";
import { RecognitionDialog, SettingsDialog, ShortcutsDialog } from "./Dialogs";
import { Grid } from "./Grid";
import { Spreadsheet } from "./Spreadsheet";
import { ColorPanel, EventPanel, GuidePanel } from "./Panels";
import { ChoiceDialog } from "./Dialogs";
import { NEUTRAL_COLOR, Transport, Viewer, type Segment, type ViewerHandle } from "./Viewer";

const isTyping = (target: EventTarget | null) =>
  target instanceof HTMLElement && (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable);

const PLAYBACK_RATES = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4];

// The left pane: its width and what is folded are per-browser conveniences.
const LEFT_MIN = 160, LEFT_MAX = 520, LEFT_DEFAULT = 216;
const clampLeft = (px: number) => Math.round(Math.max(LEFT_MIN, Math.min(LEFT_MAX, px)));
const stored = (key: string): string | null => {
  try { return localStorage.getItem(key); } catch { return null; }
};
const store = (key: string, value: string) => {
  try { localStorage.setItem(key, value); } catch { /* storage unavailable */ }
};

export function Workspace({ info, project, setProject, active, onOpenProject }: {
  info: Info; project: Project; setProject: (p: Project) => void; active: boolean; onOpenProject: () => void;
}) {
  const { t, lang, setLang } = useI18n();
  const toast = useToast();
  const viewerRef = useRef<ViewerHandle>(null);
  // File IDs repeat across projects; keep cached media local to this opened project.
  const [mediaSession] = useState(() => crypto.randomUUID?.() ?? `${Date.now()}-${Math.random()}`);
  const resume = useRef(project.settings.reviewPosition);
  const positionRef = useRef<ReviewPosition | null>(null);
  const lastSavedPosition = useRef("");
  const saveQueue = useRef(Promise.resolve());

  const [filter, setFilter] = useState<Filter>(resume.current?.filter ?? {});
  const [ids, setIds] = useState<number[]>([]);
  const [index, setIndex] = useState(0);
  const rowsRef = useRef(new Map<number, Row>());
  const [rowsVersion, setRowsVersion] = useState(0);
  const [selection, setSelection] = useState<Set<number>>(new Set());
  const anchor = useRef<number | null>(null);
  const [view, setView] = useState<"viewer" | "grid" | "table">(resume.current?.view ?? "viewer");
  const allRecords = view === "table";
  const [detail, setDetail] = useState<FileDetail | null>(null);
  // The file position (ids[index]) the detail was loaded for. A sibling event row of the same
  // file has its own position in the all-records list, so `detail.sameFileRows` cannot tell
  // "picked with the record chip" from "moved onto the sibling row and still loading".
  const [detailFor, setDetailFor] = useState<number | null>(null);
  const [videoInfo, setVideoInfo] = useState<VideoInfo | null>(null);
  const [videoInfoId, setVideoInfoId] = useState<number | null>(null);
  const frameRef = useRef(0);
  const [openEvents, setOpenEvents] = useState<RestEvent[]>([]);
  const [duplicates, setDuplicates] = useState<Record<string, number>>(project.duplicates ?? {});
  const [chooser, setChooser] = useState<null | { title: string; options: { value: string; label: string }[];
                                                   resolve: (v: string | null) => void }>(null);
  const [saving, setSaving] = useState(0);
  const [showGuides, setShowGuides] = useState(true);
  const [showBoxes, setShowBoxes] = useState(true);
  const [compare, setCompare] = useState(false);
  const [drawing, setDrawing] = useState<ShapeKind | null>(null);
  const [folderGuides, setFolderGuides] = useState<{ guides: Guide[]; source: string | null }>({ guides: [], source: null });
  const [folderColor, setFolderColor] = useState<ColorAdjust | null>(null);
  const [color, setColor] = useState<ColorAdjust>(NEUTRAL_COLOR);
  const [dialog, setDialog] = useState<null | "settings" | "shortcuts" | "recognitions">(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const closeMenus = () => { setMenuOpen(false); setExportOpen(false); };
  const [pop, setPop] = useState<null | "color" | "guide">(null);
  const [selectedEvent, setSelectedEvent] = useState<number | null>(null);
  const [palette, setPalette] = useState<Palette>(project.settings.palette ?? { items: [], single: false });
  const [canUndo, setCanUndo] = useState(project.canUndo);
  const [canRedo, setCanRedo] = useState(project.canRedo);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [tree, setTree] = useState<TreeData | null>(null);
  const [leftWidth, setLeftWidth] = useState(() => clampLeft(Number(stored("kemomichi.left.width")) || LEFT_DEFAULT));
  const [leftHidden, setLeftHidden] = useState(() => stored("kemomichi.left.hidden") === "1");
  const [filesOpen, setFilesOpen] = useState(() => stored("kemomichi.left.files") !== "0");
  const [filtersOpen, setFiltersOpen] = useState(() => stored("kemomichi.left.filters") !== "0");
  useEffect(() => {
    store("kemomichi.left.width", String(leftWidth));
    store("kemomichi.left.hidden", leftHidden ? "1" : "0");
    store("kemomichi.left.files", filesOpen ? "1" : "0");
    store("kemomichi.left.filters", filtersOpen ? "1" : "0");
  }, [leftWidth, leftHidden, filesOpen, filtersOpen]);

  const handleCapture = async () => {
    const detail = currentDetail;
    if (!detail) return;
    try {
      const dataUrl = await viewerRef.current?.capture();
      if (!dataUrl) {
        toast.push("warning", t("capture.failed"));
        return;
      }
      const baseName = detail.values.File ? detail.values.File.replace(/\.[^.]+$/, "") : `file_${detail.id}`;
      const framePart = detail.kind === "video" ? `_f${frameRef.current}` : "";
      const now = new Date();
      const pad = (n: number) => String(n).padStart(2, "0");
      const timestamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
      const filename = `${baseName}${framePart}_cap_${timestamp}.jpg`;

      await api.saveCapture(detail.id, filename, dataUrl);

      const a = document.createElement("a");
      a.href = dataUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);

      toast.push("success", t("capture.saved", { filename }));
    } catch (e) {
      toast.error(e);
    }
  };

  useEffect(() => {
    if (!active) {
      viewerRef.current?.pause();
      setCompare(false);
    }
  }, [active]);

  const controls = project.controls;
  const flagLabel = (label: string) => controls.find((c) => c.dataLabel === label)?.label ?? label;
  const locked = useMemo(() => new Set(project.lockedColumns), [project.lockedColumns]);
  const currentId = ids[index] ?? null;
  const currentRow = currentId !== null ? rowsRef.current.get(currentId) ?? null : null;
  const folder = currentRow?.values.RelativePath ?? "";
  const threshold = Number(project.settings.bboxThreshold ?? 0.2);

  const savePosition = useCallback((keepalive = false) => {
    const position = positionRef.current;
    if (!position || project.readOnly) return;
    const snapshot = JSON.stringify(position);
    if (lastSavedPosition.current === snapshot) return;
    lastSavedPosition.current = snapshot;
    const payload = JSON.parse(snapshot) as ReviewPosition;
    const write = () => api.saveReviewPosition(project.path, payload, keepalive).catch((error) => {
      if (!(error instanceof ApiError && error.status === 409)) {
        lastSavedPosition.current = "";
        if (!keepalive) toast.error(error);
      }
    });
    if (keepalive) void write();
    else saveQueue.current = saveQueue.current.then(write);
  }, [project.path, project.readOnly, toast.error]);

  useEffect(() => {
    if (currentId === null) return;
    const frame = positionRef.current?.fileId === currentId ? frameRef.current
      : resume.current?.fileId === currentId ? resume.current.frame : 0;
    frameRef.current = frame;
    positionRef.current = { fileId: currentId, frame, filter, view };
    savePosition();
  }, [currentId, filter, view, savePosition]);

  useEffect(() => {
    const timer = window.setInterval(() => savePosition(), 1000);
    const onHide = () => savePosition(true);
    const onVisibility = () => { if (document.visibilityState === "hidden") onHide(); };
    window.addEventListener("pagehide", onHide);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("pagehide", onHide);
      document.removeEventListener("visibilitychange", onVisibility);
      savePosition(true);
    };
  }, [savePosition]);

  useEffect(() => {
    api.openEvents().then(setOpenEvents).catch(() => {});
  }, [project.path]);

  useEffect(() => {
    if (project.settings.palette) setPalette(project.settings.palette);
    else api.paletteSuggest().then((p) => p && setPalette(p)).catch(() => {});
  }, [project.settings.palette]);

  // ---- loading rows ---------------------------------------------------------------------
  const storeRows = useCallback((rows: Row[]) => {
    for (const row of rows) rowsRef.current.set(row.id, row);
    setRowsVersion((v) => v + 1);
  }, []);

  const requested = useRef(new Set<number>());
  const need = useCallback((wanted: number[]) => {
    const missing = wanted.filter((id) => !rowsRef.current.has(id) && !requested.current.has(id));
    if (!missing.length) return;
    missing.forEach((id) => requested.current.add(id));
    for (let i = 0; i < missing.length; i += 400) {
      const chunk = missing.slice(i, i + 400);
      api.rowsByIds(chunk).then((r) => storeRows(r.rows)).catch(toast.error)
        .finally(() => chunk.forEach((id) => requested.current.delete(id)));
    }
  }, [storeRows, toast.error]);

  const reloadIds = useCallback(async (keep?: number | null) => {
    try {
      const list = await api.ids(filter, allRecords);
      setIds(list);
      const at = keep != null ? list.indexOf(keep) : -1;
      setIndex(at >= 0 ? at : 0);
      setSelection(new Set());
    } catch (e) {
      toast.error(e);
    }
  }, [filter, allRecords, toast.error]);

  useEffect(() => {
    const requested = currentId ?? resume.current?.fileId;
    const keep = !allRecords && requested != null ? duplicates[String(requested)] ?? requested : requested;
    reloadIds(keep);
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [filter, allRecords]);

  useEffect(() => {
    if (!ids.length) return;
    need(ids.slice(Math.max(0, index - 20), index + 40));
  }, [ids, index, need]);

  // ---- file tree (left pane) ------------------------------------------------------------
  // One entry per file whatever the view; reloaded whenever the list of files is (a new filter
  // or view arrives here as a new `ids`), and when the species that count as "entered" change.
  const treeRequest = useRef(0);
  useEffect(() => {
    const request = ++treeRequest.current;
    api.tree(filter, allRecords).then((data) => { if (request === treeRequest.current) setTree(data); }).catch(toast.error);
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [ids, duplicates, palette, toast.error]);

  // A row the page holds is fresher than the listing: a species just entered shows at once.
  const treeState = useCallback((id: number, state: number) => {
    const row = rowsRef.current.get(id);
    if (!row) return state;
    return (palette.items.some((i) => isTrue(row.values[i.flag])) ? ENTERED : 0) | (isTrue(row.values.DeleteFlag) ? DELETED : 0);
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [palette, rowsVersion]);
  // Another record of the file may be current (a record tab, a table row); the tree marks the file.
  const treeCurrent = useMemo(() => {
    if (currentId === null || !tree) return null;
    const direct = duplicates[String(currentId)] ?? currentId;
    if (tree.files.some((f) => f[0] === direct)) return direct;
    const row = rowsRef.current.get(currentId);
    if (!row) return null;
    const folderAt = tree.folders.indexOf((row.values.RelativePath ?? "").replace(/^\\+|\\+$/g, ""));
    return tree.files.find((f) => f[1] === folderAt && f[2] === row.values.File)?.[0] ?? null;
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [currentId, tree, duplicates, rowsVersion]);
  const openFromTree = (id: number, activate: boolean) => {
    const at = ids.indexOf(id);
    if (at < 0) return;
    setIndex(at);
    if (activate) setView("viewer");
  };
  const startResize = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const bar = e.currentTarget;
    const left = bar.parentElement!.getBoundingClientRect().left;
    // Captured, so the drag goes on over the viewer and ends cleanly if the pointer is taken away.
    try { bar.setPointerCapture(e.pointerId); } catch { /* an old browser: the bar still follows while over it */ }
    const ends = ["pointerup", "pointercancel", "lostpointercapture"];
    const move = (ev: PointerEvent) => setLeftWidth(clampLeft(ev.clientX - left));
    const stop = () => {
      bar.removeEventListener("pointermove", move);
      ends.forEach((name) => bar.removeEventListener(name, stop));
    };
    bar.addEventListener("pointermove", move);
    ends.forEach((name) => bar.addEventListener(name, stop));
  };

  // Only the latest request may set the detail, and only while the same file is current: an
  // older response arriving late would put another file's record on screen (and make writes
  // go to it). Callers that run after an await read the current file from the ref, not from
  // their closure, so they cannot cancel the load of a file the user has moved on to.
  const currentIdRef = useRef(currentId);
  currentIdRef.current = currentId;
  const detailRequest = useRef(0);
  const loadDetail = useCallback(async (id: number | null) => {
    const request = ++detailRequest.current;
    const forId = currentIdRef.current;
    if (id === null) {
      setDetail(null);
      setDetailFor(null);
      return;
    }
    try {
      const d = await api.file(id);
      if (request !== detailRequest.current || forId !== currentIdRef.current) return;
      setDetail(d);
      setDetailFor(forId);
      storeRows([{ id: d.id, values: d.values }]);
    } catch (e) {
      toast.error(e);
    }
  }, [storeRows, toast.error]);

  useEffect(() => { loadDetail(currentId); setSelectedEvent(null); }, [currentId, loadDetail]);

  useEffect(() => {
    let cancelled = false;
    setVideoInfo(null);
    setVideoInfoId(null);
    if (detail?.kind === "video" && detail.exists) {
      const id = detail.id;
      api.videoInfo(id).then((info) => {
        if (!cancelled) { setVideoInfo(info); setVideoInfoId(id); }
      }).catch((error) => { if (!cancelled) toast.error(error); });
    }
    return () => { cancelled = true; };
  }, [detail?.id, detail?.kind, detail?.exists, toast.error]);

  // ---- per-folder settings (guides, colour) ----------------------------------------------
  useEffect(() => {
    let cancelled = false;
    api.folderSettings(folder).then((s) => {
      if (cancelled) return;
      setFolderGuides({ guides: (s.guides as Guide[]) ?? [], source: s.guides ? folder : null });
      setFolderColor(s.color ?? null);
      setColor(s.color ?? NEUTRAL_COLOR);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [folder]);

  const saveGuides = async (guides: Guide[]) => {
    setFolderGuides({ guides, source: folder });
    try {
      await api.setFolderSetting(folder, "guides", guides);
    } catch (e) {
      toast.error(e);
    }
  };

  // ---- writing --------------------------------------------------------------------------
  // The record on screen: the file's own row, or one of its event rows picked with the record chip.
  // Until the current file's detail has loaded, `detail` may still be the previous position's:
  // it counts only when it was loaded for the current position.
  const currentDetail = detail && currentId !== null && detailFor === currentId ? detail : null;
  const recordId = currentDetail?.id ?? currentId;
  const targets = (): number[] => (view === "grid" && selection.size > 1 ? [...selection] : recordId !== null ? [recordId] : []);

  const write = useCallback(async (fileIds: number[], values: Record<string, string>) => {
    if (!fileIds.length) return;
    setSaving((n) => n + 1);
    try {
      const result = await api.update(fileIds, values);
      storeRows(result.rows);
      setCanUndo(result.canUndo);
      setCanRedo(result.canRedo);
      if (recordId !== null && fileIds.includes(recordId)) {
        const row = result.rows.find((r) => r.id === recordId);
        if (row) setDetail((d) => (d && d.id === row.id ? { ...d, values: row.values } : d));
      }
    } finally {
      setSaving((n) => n - 1);
    }
  }, [recordId, storeRows]);

  const change = async (values: Record<string, string>, confirmText?: string) => {
    if (confirmText && !window.confirm(confirmText)) return;
    try {
      await write(targets(), values);
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) throw e;  // shown next to the field
      toast.error(e);
    }
  };

  const history = async (redo: boolean) => {
    const startedOn = currentIdRef.current;
    try {
      const result = redo ? await api.redo() : await api.undo();
      storeRows(result.rows);
      setCanUndo(result.canUndo);
      setCanRedo(result.canRedo);
      if (currentIdRef.current === startedOn && recordId !== null && result.fileIds.includes(recordId)) loadDetail(recordId);
    } catch (e) {
      toast.error(e);
    }
  };

  const copyPrevious = async () => {
    if (index < 1 || currentId === null) return;
    const prev = rowsRef.current.get(ids[index - 1]) ?? (await api.file(ids[index - 1]));
    const values: Record<string, string> = {};
    for (const c of controls) {
      if (!c.standard && c.copyable && !locked.has(c.dataLabel)) values[c.dataLabel] = prev.values[c.dataLabel] ?? "";
    }
    // Palette species and counts are copied too, so a burst of the same animal is one key away.
    for (const item of palette.items) {
      values[item.flag] = prev.values[item.flag] ?? "false";
      if (item.counter) values[item.counter] = prev.values[item.counter] ?? "0";
    }
    try {
      await write([recordId ?? currentId], values);
    } catch (e) {
      toast.error(e);
    }
  };

  const duplicateRecord = async () => {
    if (!currentDetail || project.readOnly) return;
    try {
      const res = await api.duplicateFile(currentDetail.id);
      toast.push("success", t("data.duplicated"));
      const newIds = await api.ids(filter, allRecords);
      setIds(newIds);
      rowsRef.current.set(res.row.id, res.row);
      setRowsVersion((v) => v + 1);
      const newIdx = newIds.indexOf(res.id);
      if (newIdx >= 0) {
        setIndex(newIdx);
      }
    } catch (e) {
      toast.error(e);
    }
  };

  // ---- REST events (entry to exit, possibly across files) --------------------------------
  const frameNow = () => (currentDetail?.kind === "video" ? viewerRef.current?.currentFrame() ?? 0 : null);

  const applyEventResult = useCallback(async (result: EventResult) => {
    storeRows(result.rows);
    setOpenEvents(result.open);
    setDuplicates(result.duplicates);
    if (result.warning) toast.push("warning", t(result.warning));
    // Rows may have been added or removed (one row per event), so refresh the list and this file.
    await reloadIds(currentIdRef.current);
    loadDetail(currentIdRef.current);
  }, [storeRows, toast, t, reloadIds, loadDetail]);

  const choose = (title: string, options: { value: string; label: string }[]) =>
    new Promise<string | null>((resolve) => setChooser({ title, options, resolve }));

  const startEvent = async (inside: boolean) => {
    if (!currentDetail || project.readOnly) return;
    const row = rowsRef.current.get(currentDetail.id);
    const on = palette.items.filter((i) => row && isTrue(row.values[i.flag]));
    // Skip the question only for a file's first event with exactly one species on; afterwards the row's
    // species may just be the previous event's, so always ask.
    let species = on.length === 1 && currentDetail.events.length === 0 ? on[0].flag : null;
    if (species === null && palette.items.length) {
      species = await choose(t("event.chooseSpecies"), palette.items.map((i) => ({ value: i.flag, label: flagLabel(i.flag) })));
      if (species === null) return;
    }
    try {
      await applyEventResult(await api.startEvent({ fileId: currentDetail.id, frame: inside ? null : frameNow(), inside,
                                                    species: species ?? "" }));
    } catch (e) {
      toast.error(e);
    }
  };

  const endEvent = async (inside: boolean, target?: RestEvent) => {
    if (!currentDetail || project.readOnly) return;
    let event = target ?? null;
    if (!event) {
      if (openEvents.length === 0) {
        toast.push("info", t("event.noneOpen"));
        return;
      }
      if (openEvents.length === 1) event = openEvents[0];
      else {
        const picked = await choose(t("event.chooseOpen"), openEvents.map((e) => ({
          value: String(e.id),
          label: `${flagLabel(e.species) || "—"} #${e.individual} · ${e.startFile}`
            + (e.start_inside ? ` · ${t("event.fromStart")}` : ` · ${e.entrySeconds ?? ""}s`),
        })));
        if (picked === null) return;
        event = openEvents.find((e) => String(e.id) === picked) ?? null;
      }
    }
    if (!event) return;
    try {
      await applyEventResult(await api.endEvent(event.id, { fileId: currentDetail.id, frame: inside ? null : frameNow(), inside }));
    } catch (e) {
      toast.error(e);
    }
  };

  const eventAction = async (run: () => Promise<EventResult>) => {
    try {
      await applyEventResult(await run());
    } catch (e) {
      toast.error(e);
    }
  };

  const jumpEvent = (e: RestEvent, where: "start" | "end") => {
    const fileId = where === "start" ? e.start_file_id : e.end_file_id;
    const frame = where === "start" ? e.start_frame : e.end_frame;
    if (fileId === null) return;
    const seek = () => frame !== null && setTimeout(() => viewerRef.current?.seekFrame(frame), 600);
    if (detail && (detail.id === fileId || detail.sameFileRows.includes(fileId))) {
      if (frame !== null) viewerRef.current?.seekFrame(frame);
      return;
    }
    const at = ids.indexOf(fileId);
    if (at >= 0) {
      setIndex(at);
      setView("viewer");
      seek();
    }
  };

  const segments: Segment[] = useMemo(() => {
    if (!detail || detail.kind !== "video") return [];
    const mine = new Set(detail.sameFileRows);
    const last = Math.max(0, (videoInfo?.frameTimes?.length ?? 1) - 1);
    const all = [...detail.events, ...openEvents.filter((o) => !detail.events.some((e) => e.id === o.id))];
    return all.filter((e) => mine.has(e.start_file_id) || (e.end_file_id !== null && mine.has(e.end_file_id)) || e.open)
      .map((e) => {
        const startsHere = mine.has(e.start_file_id);
        const endsHere = e.end_file_id !== null && mine.has(e.end_file_id);
        const start = startsHere ? (e.start_inside ? 0 : e.start_frame ?? 0) : 0;
        const end = e.open ? null : endsHere ? (e.end_inside ? last : e.end_frame ?? last) : last;
        return { key: e.id, start, end, label: `#${e.individual} ${flagLabel(e.species)}${end === null ? ` · ${t("event.open")}` : ""}`,
                 carriedIn: !startsHere || e.start_inside, carriedOut: !e.open && !endsHere };
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail, openEvents, videoInfo]);

  // ---- navigation and keys ----------------------------------------------------------------
  const go = (delta: number) => setIndex((i) => Math.max(0, Math.min(ids.length - 1, i + delta)));

  const toggleSpecies = (key: string) => {
    const item = palette.items.find((i) => i.key === key);
    if (!item || project.readOnly) return;
    const ids_ = targets();
    // One file: wait for its record, as the palette buttons do (they are disabled until then).
    if (!ids_.length || (ids_.length === 1 && !currentDetail)) return;
    const row = ids_.length === 1 ? rowsRef.current.get(ids_[0]) ?? null : null;
    const on = row ? !isTrue(row.values[item.flag]) : true;
    change(speciesChange(palette, row, item.flag, on));
  };

  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (dialog || chooser || isTyping(e.target)) return;
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "z") {
        e.preventDefault();
        history(e.shiftKey);
        return;
      }
      if (mod && e.key.toLowerCase() === "y") {
        e.preventDefault();
        history(true);
        return;
      }
      if (mod && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "b") {
        e.preventDefault();
        setLeftHidden((v) => !v);
        return;
      }
      if (mod || e.altKey) return;
      switch (e.key) {
        case "ArrowRight": e.preventDefault(); go(1); break;
        case "ArrowLeft": e.preventDefault(); go(-1); break;
        case ".": viewerRef.current?.step(e.shiftKey ? 10 : 1); break;
        case ",": viewerRef.current?.step(e.shiftKey ? -10 : -1); break;
        case ">": viewerRef.current?.step(10); break;
        case "<": viewerRef.current?.step(-10); break;
        case " ": e.preventDefault(); viewerRef.current?.togglePlay(); break;
        case "c": case "C": handleCapture(); break;
        case "[": {
          const idx = PLAYBACK_RATES.indexOf(playbackRate);
          const next = idx > 0 ? PLAYBACK_RATES[idx - 1] : PLAYBACK_RATES[0];
          setPlaybackRate(next);
          break;
        }
        case "]": {
          const idx = PLAYBACK_RATES.indexOf(playbackRate);
          const next = idx >= 0 && idx < PLAYBACK_RATES.length - 1 ? PLAYBACK_RATES[idx + 1] : PLAYBACK_RATES[PLAYBACK_RATES.length - 1];
          setPlaybackRate(next);
          break;
        }
        case "s": case "S": startEvent(e.shiftKey); break;
        case "e": case "E": endEvent(e.shiftKey); break;
        case "g": case "G": setShowGuides((v) => !v); break;
        case "b": case "B": setShowBoxes((v) => !v); break;
        case "a": case "A": setCompare(true); break;
        case "v": case "V": setView((v) => (v === "viewer" ? "grid" : v === "grid" ? "table" : "viewer")); break;
        case "f": case "F": viewerRef.current?.fit(); break;
        case "d": case "D":
          if (currentRow) change({ DeleteFlag: isTrue(currentRow.values.DeleteFlag) ? "false" : "true" });
          break;
        case "?": setDialog("shortcuts"); break;
        case "Escape": setDrawing(null); setPop(null); closeMenus(); break;
        default:
          if (/^[0-9]$/.test(e.key)) toggleSpecies(e.key);
      }
    };
    const onUp = (e: KeyboardEvent) => {
      if (e.key === "a" || e.key === "A") setCompare(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("keyup", onUp);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("keyup", onUp);
    };
  });

  // ---- grid selection --------------------------------------------------------------------
  const pick = (id: number, at: number, e: React.MouseEvent) => {
    setIndex(at);
    setSelection((prev) => {
      if (e.shiftKey && anchor.current !== null) {
        const a = Math.min(anchor.current, at), b = Math.max(anchor.current, at);
        return new Set([...prev, ...ids.slice(a, b + 1)]);
      }
      anchor.current = at;
      if (e.ctrlKey || e.metaKey) {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id); else next.add(id);
        return next;
      }
      return new Set([id]);
    });
  };

  // ---- filters ---------------------------------------------------------------------------
  const speciesLabels = (row: Row) => palette.items.filter((i) => isTrue(row.values[i.flag])).map((i) => {
    const n = i.counter ? row.values[i.counter] : "";
    return flagLabel(i.flag) + (n && n !== "0" && n !== "1" ? ` ×${n}` : "");
  });
  const toggleAny = (flag: string) => {
    const current = new Set(filter.anyTrue ?? []);
    if (current.has(flag)) current.delete(flag); else current.add(flag);
    setFilter({ ...filter, anyTrue: [...current], allFalse: undefined });
  };
  const categoryLabel = (d: Detection) =>
    (d.classification ? project.categories.classification[d.classification] : undefined) ??
    project.categories.detection[d.category] ?? d.category;


  const total = ids.length;
  const activeFilters = [filter.folder, filter.text, filter.deleted, filter.detection, filter.anyTrue?.length, filter.allFalse?.length]
    .filter(Boolean).length;
  const bulkCount = view === "grid" ? selection.size : 0;
  const frameTimes = videoInfo?.frameTimes ?? [];
  void rowsVersion;

  const exportTo = async (kind: "csv" | "events") => {
    closeMenus();
    try {
      const { path } = kind === "csv" ? await api.exportCsv() : await api.exportEvents();
      toast.push("success", t("csv.done", { path }));
    } catch (e) { toast.error(e); }
  };
  const noEvent = project.readOnly || !currentDetail;
  const eventButtons = (
    <>
      <span className="split">
        <button type="button" className="btn" disabled={noEvent} onClick={() => startEvent(false)}
                title={`${t("event.entry")} (S)`}>{t("event.entry")} <kbd>S</kbd></button>
        <button type="button" className="btn" disabled={noEvent} onClick={() => startEvent(true)}
                title="Shift+S">{t("event.fromStart")}</button>
      </span>
      <span className="split">
        <button type="button" className="btn" disabled={noEvent} onClick={() => endEvent(false)}
                title={`${t("event.exit")} (E)`}>{t("event.exit")} <kbd>E</kbd></button>
        <button type="button" className="btn" disabled={noEvent} onClick={() => endEvent(true)}
                title="Shift+E">{t("event.toEnd")}</button>
      </span>
    </>
  );
  const selectSegment = (key: number) => {
    setSelectedEvent(key);
    const e = [...(detail?.events ?? []), ...openEvents].find((x) => x.id === key);
    if (e) jumpEvent(e, "start");
  };
  const records = detail ? (detail.sameFileRows.length ? detail.sameFileRows : [detail.id]) : [];

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">{t("app.name")}</span>
        <span className="project" title={project.path}>{project.name}</span>
        <span className={`tag${saving ? " saving" : ""}`} role="status" data-testid="save-state">
          {project.readOnly ? t("top.readOnly") : saving ? t("top.saving") : t("top.saved")}
        </span>
        <button className="ib" disabled={!canUndo || project.readOnly} onClick={() => history(false)}
                aria-label={t("top.undo")} title={`${t("top.undo")} (Ctrl+Z)`}>↶</button>
        <button className="ib" disabled={!canRedo || project.readOnly} onClick={() => history(true)}
                aria-label={t("top.redo")} title={`${t("top.redo")} (Ctrl+Shift+Z)`}>↷</button>
        <span className="spacer" />
        <span className="anchor">
          <button className="btn main small" aria-haspopup="menu" aria-expanded={exportOpen}
                  onClick={() => { setMenuOpen(false); setExportOpen((v) => !v); }}>{t("top.export")} ▾</button>
          {exportOpen && (
            <div className="menu" role="menu" onMouseLeave={() => setExportOpen(false)}>
              <button role="menuitem" onClick={() => exportTo("csv")}>{t("menu.exportCsv")}</button>
              <button role="menuitem" onClick={() => exportTo("events")}>{t("menu.exportEvents")}</button>
            </div>
          )}
        </span>
        <span className="anchor">
          <button className="ib" aria-haspopup="menu" aria-expanded={menuOpen} aria-label={t("top.more")} title={t("top.more")}
                  onClick={() => { setExportOpen(false); setMenuOpen((v) => !v); }}>⋯</button>
          {menuOpen && (
            <div className="menu" role="menu" onMouseLeave={() => setMenuOpen(false)}>
              <button role="menuitem" disabled={saving > 0} onClick={() => { closeMenus(); onOpenProject(); }}>{t("menu.open")}</button>
              <button role="menuitem" disabled={project.readOnly || !currentDetail || bulkCount > 1} onClick={() => { closeMenus(); void duplicateRecord(); }}>{t("data.duplicate")}</button>
              <button role="menuitem" disabled={project.readOnly} onClick={() => { closeMenus(); setDialog("recognitions"); }}>{t("menu.importRecognitions")}</button>
              <hr />
              <button role="menuitem" onClick={() => { closeMenus(); setDialog("settings"); }}>{t("menu.settings")}</button>
              <button role="menuitem" onClick={() => { closeMenus(); setDialog("shortcuts"); }}>{t("menu.shortcuts")}</button>
              <button role="menuitem" onClick={() => setLang(lang === "ja" ? "en" : "ja")}>{lang === "ja" ? "English" : "日本語"}</button>
              <hr />
              <div className="menu-note">{info.serverMode ? t("top.server", { host: location.host }) : t("top.thisPc")}</div>
            </div>
          )}
        </span>
      </header>
      {project.readOnly && <div className="ro-banner">! {t(project.readOnlyReason || "readOnly.requested")}</div>}

      <div className={"panes" + (leftHidden ? " left-hidden" : "")} style={{ "--km-left": `${leftWidth}px` } as React.CSSProperties}>
        {leftHidden ? (
          <aside className="pane left rail" aria-label={t("nav.find")}>
            <button className="icon-btn" aria-label={t("nav.show")} title={t("nav.show")} onClick={() => setLeftHidden(false)}>»</button>
          </aside>
        ) : (
        <aside className="pane left" aria-label={t("nav.find")}>
          <section className={"sec files" + (filesOpen ? " unfolded" : "")}>
            <div className="ph">
              <button className="sec-toggle" aria-expanded={filesOpen} onClick={() => setFilesOpen((v) => !v)}>
                <span aria-hidden="true">{filesOpen ? "▾" : "▸"}</span> {t("nav.files")}
              </button>
              <span className="cnt" data-testid="match-count">{t("filter.count", { count: total })}</span>
              <button className="icon-btn small" aria-label={t("nav.hide")} title={t("nav.hide")} onClick={() => setLeftHidden(true)}>«</button>
            </div>
            {filesOpen && (
              <FileTree data={tree} currentId={treeCurrent} stateOf={treeState}
                        storageKey={`kemomichi.tree.${project.path}`} filterFolder={filter.folder}
                        onFilterFolder={(path) => setFilter({ ...filter, folder: path })} onOpen={openFromTree} />
            )}
          </section>
          <section className={"sec filters" + (filtersOpen ? " unfolded" : "")}>
            <div className="ph">
              <button className="sec-toggle" aria-expanded={filtersOpen} onClick={() => setFiltersOpen((v) => !v)}>
                <span aria-hidden="true">{filtersOpen ? "▾" : "▸"}</span> {t("nav.filters")}
              </button>
              {activeFilters > 0 && <span className="cnt">{t("filter.active", { count: activeFilters })}</span>}
            </div>
            {filtersOpen && (
          <div className="pane-body">
            {filter.folder && (
              <div className="chips">
                <button className="chip" aria-pressed="true" onClick={() => setFilter({ ...filter, folder: undefined })}>
                  {t("filter.folder", { name: filter.folder.split("\\").pop() ?? "" })} ×
                </button>
              </div>
            )}
            <input type="text" placeholder={t("filter.search")} aria-label={t("filter.search")} defaultValue={filter.text ?? ""}
                   onKeyDown={(e) => e.key === "Enter" && setFilter({ ...filter, text: (e.target as HTMLInputElement).value || undefined })}
                   onBlur={(e) => (e.target.value || undefined) !== filter.text && setFilter({ ...filter, text: e.target.value || undefined })} />
            <div className="chips">
              {palette.items.map((i) => (
                <button key={i.flag} className="chip" aria-pressed={(filter.anyTrue ?? []).includes(i.flag)}
                        onClick={() => toggleAny(i.flag)}>{flagLabel(i.flag)}</button>
              ))}
            </div>
            <div className="chips">
              <button className="chip" aria-pressed={!!filter.allFalse}
                      onClick={() => setFilter({ ...filter, anyTrue: undefined,
                        allFalse: filter.allFalse ? undefined : palette.items.map((i) => i.flag) })}>
                {t("filter.unentered")}
              </button>
              <button className="chip" aria-pressed={filter.deleted === true}
                      onClick={() => setFilter({ ...filter, deleted: filter.deleted ? undefined : true })}>{t("filter.deleted")}</button>
            </div>
            {project.hasRecognitions && (
              <div className="field">
                <label htmlFor="det-filter">{t("filter.detection")}</label>
                <select id="det-filter" value={filter.detection?.category ?? ""}
                        onChange={(e) => setFilter({ ...filter, detection: e.target.value ? { category: e.target.value, minConf: threshold } : null })}>
                  <option value="">—</option>
                  <option value="any">{t("filter.detectionAny")}</option>
                  <option value="none">{t("filter.detectionNone")}</option>
                  {Object.entries(project.categories.detection).filter(([k]) => k !== "0").map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
                {filter.detection && <span className="note">{t("filter.minConf", { value: threshold })}</span>}
              </div>
            )}
            <button className="btn text small" onClick={() => setFilter({})} style={{ alignSelf: "flex-start" }}>{t("filter.clear")}</button>
          </div>
            )}
          </section>
          <div className="resizer" role="separator" aria-orientation="vertical" aria-label={t("nav.resize")} tabIndex={0}
               aria-valuenow={leftWidth} aria-valuemin={LEFT_MIN} aria-valuemax={LEFT_MAX} onPointerDown={startResize}
               onDoubleClick={() => setLeftWidth(LEFT_DEFAULT)}
               onKeyDown={(e) => {
                 if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
                 e.preventDefault();
                 e.stopPropagation();
                 setLeftWidth((w) => clampLeft(w + (e.key === "ArrowRight" ? 16 : -16)));
               }} />
        </aside>
        )}

        <main className="center">
          <div className="cbar">
            <div className="seg" role="group" aria-label={t("view.label")}>
              <button aria-pressed={view === "viewer"} onClick={() => setView("viewer")}>{t("view.viewer")}</button>
              <button aria-pressed={view === "grid"} onClick={() => setView("grid")}>{t("view.grid")}</button>
              <button aria-pressed={view === "table"} onClick={() => setView("table")}>{t("view.table")}</button>
            </div>
            <div className="nav">
              <button className="icon-btn" onClick={() => go(-1)} disabled={index <= 0} aria-label={t("video.prevFile")}>←</button>
              <span className="pos" data-testid="position">{t("viewer.position", { index: total ? index + 1 : 0, total })}</span>
              <button className="icon-btn" onClick={() => go(1)} disabled={index >= total - 1} aria-label={t("video.nextFile")}>→</button>
            </div>
            {currentRow && <span className="fname" title={currentRow.values.RelativePath} data-testid="file-name">{currentRow.values.File} · {currentRow.values.DateTime}</span>}
          </div>
          {view === "grid" ? (
            <Grid mediaSession={mediaSession} ids={ids} rows={rowsRef.current} need={need} selection={selection} currentId={currentId}
                  duplicates={duplicates}
                  onPick={pick} onOpen={(at) => { setIndex(at); setView("viewer"); }} speciesLabels={speciesLabels} />
          ) : view === "table" ? (
            <Spreadsheet
              mediaSession={mediaSession}
              ids={ids}
              rows={rowsRef.current}
              need={need}
              currentId={currentId}
              onPick={(id, at) => {
                setIndex(at);
                setSelection(new Set([id]));
              }}
              onOpen={(at) => {
                setIndex(at);
                setView("viewer");
              }}
              controls={controls}
              locked={locked}
              readOnly={project.readOnly}
              onWrite={write}
            />
          ) : (
            <>
              <div className="stagewrap">
                <div className="tools" role="toolbar" aria-label={t("viewer.tools")}>
                  <button onClick={() => viewerRef.current?.fit()} title={`${t("viewer.fit")} (F)`}>
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></svg>{t("viewer.fit")}
                  </button>
                  <button aria-expanded={pop === "color"} onClick={() => setPop((p) => (p === "color" ? null : "color"))}>
                    <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" /></svg>{t("viewer.color")}
                  </button>
                  <button aria-expanded={pop === "guide"} onClick={() => setPop((p) => (p === "guide" ? null : "guide"))}>
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 18L21 6" /><circle cx="3" cy="18" r="1.5" /><circle cx="21" cy="6" r="1.5" /></svg>{t("viewer.guides")}
                  </button>
                  {project.hasRecognitions && (
                    <button aria-pressed={showBoxes} onClick={() => setShowBoxes((v) => !v)} title={`${t("viewer.bboxes")} (B)`}>
                      <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="6" width="16" height="12" strokeDasharray="3 2" /></svg>{t("viewer.bboxes")}
                    </button>
                  )}
                  <hr />
                  <button onClick={handleCapture} title={`${t("viewer.capture")} (C)`}>
                    <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="7" width="18" height="13" rx="2" /><circle cx="12" cy="13.5" r="3.5" /><path d="M8 7l2-3h4l2 3" /></svg>{t("viewer.capture")}
                  </button>
                </div>
                <Viewer key={detail?.id ?? "empty"} ref={viewerRef} mediaSession={mediaSession} detail={detail}
                        initialFrame={positionRef.current?.fileId === detail?.id ? (positionRef.current?.frame ?? 0) : 0}
                        onPositionCommit={() => savePosition()}
                        missingPath={currentRow ? `${currentRow.values.RelativePath}\\${currentRow.values.File}` : ""}
                        color={color} compare={compare}
                        guides={folderGuides.guides} showGuides={showGuides}
                        detections={detail?.detections ?? []} showBoxes={showBoxes} boxThreshold={threshold}
                        categoryLabel={categoryLabel}
                        drawing={drawing}
                        onDrawn={(shape, points) => {
                          const name = `${t(`guide.${shape}`)} ${folderGuides.guides.length + 1}`;
                          saveGuides([...folderGuides.guides, { id: crypto.randomUUID?.() ?? String(Date.now()), shape, points, name, color: "#FFFFFF", width: 2 }]);
                          setDrawing(null);
                        }}
                        videoInfo={videoInfoId === detail?.id ? videoInfo : null}
                        playbackRate={playbackRate}
                        onFrame={(f) => {
                          frameRef.current = f;
                          if (positionRef.current && positionRef.current.fileId === detail?.id) positionRef.current.frame = f;
                        }} />
                {pop === "color" && (
                  <ColorPanel value={color} onChange={setColor} hasFolderDefault={folderColor !== null} readOnly={project.readOnly}
                              onClose={() => setPop(null)}
                              onSaveFolder={async () => {
                                try {
                                  await api.setFolderSetting(folder, "color", color);
                                  setFolderColor(color);
                                  toast.push("success", t("color.folderSaved"));
                                } catch (e) { toast.error(e); }
                              }}
                              onClearFolder={async () => {
                                try {
                                  await api.setFolderSetting(folder, "color", null);
                                  setFolderColor(null);
                                } catch (e) { toast.error(e); }
                              }} />
                )}
                {pop === "guide" && (
                  <GuidePanel guides={folderGuides.guides}
                              inheritedFrom={folderGuides.source !== null && folderGuides.source !== folder ? folderGuides.source : null}
                              drawing={drawing} onDraw={setDrawing} show={showGuides} onShow={setShowGuides}
                              onClose={() => setPop(null)}
                              onChange={saveGuides} readOnly={project.readOnly} />
                )}
              </div>
              {detail?.kind === "video" && videoInfo && videoInfo.available !== false ? (
                <FrameTransport viewerRef={viewerRef} frameTimes={frameTimes} exact={!!videoInfo.exactTimes}
                                segments={segments} selected={selectedEvent} onSelect={selectSegment}
                                playbackRate={playbackRate} onPlaybackRateChange={setPlaybackRate}
                                onPrevFile={() => go(-1)} onNextFile={() => go(1)} canPrev={index > 0} canNext={index < total - 1}
                                eventButtons={eventButtons} />
              ) : (
                <Transport message={detail?.kind === "video" ? (videoInfo?.available === false ? t("video.noFfmpeg") : t("video.loading")) : undefined}
                           onPrevFile={() => go(-1)} onNextFile={() => go(1)} canPrev={index > 0} canNext={index < total - 1}
                           eventButtons={eventButtons} />
              )}
            </>
          )}
        </main>

        <aside className="pane right" aria-label={t("data.record")}>
          <div className="ph">{t("data.record")}{currentRow && <span className="cnt" title={currentRow.values.RelativePath}>{currentRow.values.File}</span>}</div>
          {currentDetail && bulkCount <= 1 && (
            <div className="rtabs" role="tablist" aria-label={t("data.record")}>
              {records.map((id, i) => (
                <button key={id} role="tab" aria-selected={id === currentDetail.id} onClick={() => id !== currentDetail.id && loadDetail(id)}>
                  {t("data.recordN", { n: i + 1 })}
                </button>
              ))}
              <button type="button" disabled={project.readOnly} onClick={() => void duplicateRecord()}
                      aria-label={t("data.addRecord")} title={t("data.addRecord")}>＋</button>
            </div>
          )}
          <DataPanel controls={controls} row={currentDetail ? { id: currentDetail.id, values: currentDetail.values } : null}
                     palette={palette} locked={locked} readOnly={project.readOnly} bulkCount={bulkCount}
                     onChange={change} onCopyPrevious={copyPrevious} canCopyPrevious={index > 0}
                     onNext={() => go(1)} canNext={index < total - 1}
                     afterSpecies={currentDetail && bulkCount <= 1 && (
                       <EventPanel fileId={currentDetail.sameFileRows[0] ?? currentDetail.id} sameFileRows={currentDetail.sameFileRows}
                                   events={currentDetail.events}
                                   openEvents={openEvents} speciesLabel={flagLabel} palette={palette.items}
                                   configured={Object.entries(project.eventColumns ?? {}).some(([k, v]) =>
                                     ["speciesName", "individual", "entry", "exit", "exitFile", "startInside", "endInside", "duration"].includes(k) && !!v)}
                                   readOnly={project.readOnly}
                                   selected={selectedEvent}
                                   onSelect={(e) => { setSelectedEvent(e.id); jumpEvent(e, "start"); }}
                                   onDelete={(id) => { if (window.confirm(t("event.confirmDelete"))) eventAction(() => api.deleteEvent(id)); }}
                                   onJump={jumpEvent} onEnd={(e, inside) => endEvent(inside, e)}
                                   onReopen={(e) => eventAction(() => api.changeEvent(e.id, { reopen: true }))}
                                   onSpecies={(e, species) => eventAction(() => api.changeEvent(e.id, { species }))}
                                   onIndividual={(e, individual) => eventAction(() => api.changeEvent(e.id, { individual }))} />
                     )} />
        </aside>
      </div>

      {dialog === "settings" && (
        <SettingsDialog project={project} palette={palette} onClose={() => setDialog(null)}
                        onProject={(p) => { setProject(p); rowsRef.current.clear(); setRowsVersion((v) => v + 1); reloadIds(currentId); }} />
      )}
      {dialog === "shortcuts" && <ShortcutsDialog onClose={() => setDialog(null)} />}
      {chooser && (
        <ChoiceDialog title={chooser.title} options={chooser.options}
                      onDone={(v) => { chooser.resolve(v); setChooser(null); }} />
      )}
      {dialog === "recognitions" && (
        <RecognitionDialog info={info} project={project} onClose={() => setDialog(null)}
                           onDone={async () => { setProject(await api.project()); loadDetail(currentId); }} />
      )}
    </div>
  );
}

/** Keeps its own frame state so the rest of the workspace does not re-render on every frame. */
function FrameTransport({ viewerRef, frameTimes, exact, segments, selected, onSelect, playbackRate, onPlaybackRateChange,
                          onPrevFile, onNextFile, canPrev, canNext, eventButtons }: {
  viewerRef: React.RefObject<ViewerHandle>; frameTimes: number[]; exact: boolean; segments: Segment[];
  selected: number | null; onSelect: (key: number) => void;
  playbackRate: number; onPlaybackRateChange: (rate: number) => void;
  onPrevFile: () => void; onNextFile: () => void; canPrev: boolean; canNext: boolean; eventButtons: React.ReactNode;
}) {
  const [frame, setFrame] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const f = viewerRef.current?.currentFrame() ?? 0;
      setFrame((old) => (old === f ? old : f));
      const p = viewerRef.current?.isPlaying() ?? false;
      setIsPlaying((old) => (old === p ? old : p));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [viewerRef]);
  return (
    <Transport onPrevFile={onPrevFile} onNextFile={onNextFile} canPrev={canPrev} canNext={canNext} eventButtons={eventButtons}
               video={{
                 frame, total: frameTimes.length, frameTimes, segments, exact, selected, onSelect,
                 playbackRate, onPlaybackRateChange, isPlaying,
                 onSeek: (f) => viewerRef.current?.seekFrame(f),
                 onTogglePlay: () => viewerRef.current?.togglePlay(),
                 onStep: (delta) => viewerRef.current?.step(delta),
                 onStop: () => { viewerRef.current?.pause(); viewerRef.current?.seekFrame(0); },
               }} />
  );
}
