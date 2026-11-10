import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import type { ColorAdjust, Detection, FileDetail, Filter, Guide, Info, Interval, Palette, Project, Row, ShapeKind, VideoInfo } from "../types";
import { useToast } from "../ui";
import { DataPanel, isTrue, speciesChange } from "./DataPanel";
import { RecognitionDialog, SettingsDialog, ShortcutsDialog } from "./Dialogs";
import { Grid } from "./Grid";
import { ColorPanel, GuidePanel, RestPanel, type PendingStart } from "./Panels";
import { NEUTRAL_COLOR, Timeline, Viewer, type ViewerHandle } from "./Viewer";

const isTyping = (target: EventTarget | null) =>
  target instanceof HTMLElement && (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable);

export function Workspace({ info, project, setProject, active, onOpenProject }: {
  info: Info; project: Project; setProject: (p: Project) => void; active: boolean; onOpenProject: () => void;
}) {
  const { t, lang, setLang } = useI18n();
  const toast = useToast();
  const viewerRef = useRef<ViewerHandle>(null);
  // File IDs repeat across projects; keep cached media local to this opened project.
  const [mediaSession] = useState(() => crypto.randomUUID?.() ?? `${Date.now()}-${Math.random()}`);

  const [filter, setFilter] = useState<Filter>({});
  const [ids, setIds] = useState<number[]>([]);
  const [index, setIndex] = useState(0);
  const rowsRef = useRef(new Map<number, Row>());
  const [rowsVersion, setRowsVersion] = useState(0);
  const [selection, setSelection] = useState<Set<number>>(new Set());
  const anchor = useRef<number | null>(null);
  const [view, setView] = useState<"viewer" | "grid">("viewer");
  const [detail, setDetail] = useState<FileDetail | null>(null);
  const [videoInfo, setVideoInfo] = useState<VideoInfo | null>(null);
  const frameRef = useRef(0);
  const [pending, setPending] = useState<PendingStart | null>(null);
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
  const [palette, setPalette] = useState<Palette>(project.settings.palette ?? { items: [], single: false });
  const [canUndo, setCanUndo] = useState(project.canUndo);
  const [canRedo, setCanRedo] = useState(project.canRedo);

  useEffect(() => {
    if (!active) {
      viewerRef.current?.pause();
      setCompare(false);
    }
  }, [active]);

  const controls = project.controls;
  const locked = useMemo(() => new Set(project.lockedColumns), [project.lockedColumns]);
  const currentId = ids[index] ?? null;
  const currentRow = currentId !== null ? rowsRef.current.get(currentId) ?? null : null;
  const folder = currentRow?.values.RelativePath ?? "";
  const threshold = Number(project.settings.bboxThreshold ?? 0.2);

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
      const list = await api.ids(filter);
      setIds(list);
      const at = keep != null ? list.indexOf(keep) : -1;
      setIndex(at >= 0 ? at : 0);
      setSelection(new Set());
    } catch (e) {
      toast.error(e);
    }
  }, [filter, toast.error]);

  useEffect(() => { reloadIds(currentId); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [filter]);

  useEffect(() => {
    if (!ids.length) return;
    need(ids.slice(Math.max(0, index - 20), index + 40));
  }, [ids, index, need]);

  const loadDetail = useCallback(async (id: number | null) => {
    if (id === null) {
      setDetail(null);
      return;
    }
    try {
      const d = await api.file(id);
      setDetail(d);
      storeRows([{ id: d.id, values: d.values }]);
    } catch (e) {
      toast.error(e);
    }
  }, [storeRows, toast.error]);

  useEffect(() => { loadDetail(currentId); }, [currentId, loadDetail]);

  useEffect(() => {
    setVideoInfo(null);
    if (detail?.kind === "video" && detail.exists) {
      api.videoInfo(detail.id).then(setVideoInfo).catch(toast.error);
    }
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
  const targets = (): number[] => (view === "grid" && selection.size > 1 ? [...selection] : currentId !== null ? [currentId] : []);

  const write = useCallback(async (fileIds: number[], values: Record<string, string>) => {
    if (!fileIds.length) return;
    setSaving((n) => n + 1);
    try {
      const result = await api.update(fileIds, values);
      storeRows(result.rows);
      setCanUndo(result.canUndo);
      setCanRedo(result.canRedo);
      if (currentId !== null && fileIds.includes(currentId)) {
        const row = result.rows.find((r) => r.id === currentId);
        if (row) setDetail((d) => (d && d.id === row.id ? { ...d, values: row.values } : d));
      }
    } finally {
      setSaving((n) => n - 1);
    }
  }, [currentId, storeRows]);

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
    try {
      const result = redo ? await api.redo() : await api.undo();
      storeRows(result.rows);
      setCanUndo(result.canUndo);
      setCanRedo(result.canRedo);
      if (currentId !== null && result.fileIds.includes(currentId)) loadDetail(currentId);
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
      await write([currentId], values);
    } catch (e) {
      toast.error(e);
    }
  };

  // ---- S/E -------------------------------------------------------------------------------
  const markStart = () => {
    if (!detail || project.readOnly) return;
    if (detail.kind === "video") {
      const frame = viewerRef.current?.currentFrame() ?? 0;
      setPending({ kind: "video", fileId: detail.id, frame, label: `#${frame}` });
    } else {
      setPending({ kind: "sequence", fileId: detail.id, label: detail.values.File });
    }
  };

  const markEnd = async () => {
    if (!detail || !pending || project.readOnly) return;
    try {
      let result;
      if (pending.kind === "video") {
        if (pending.fileId !== detail.id) return;
        result = await api.createInterval({ kind: "video", fileId: detail.id, startFrame: pending.frame,
                                            endFrame: viewerRef.current?.currentFrame() ?? 0 });
      } else {
        result = await api.createInterval({ kind: "sequence", startFileId: pending.fileId, endFileId: detail.id });
      }
      setPending(null);
      storeRows([result.row]);
      if (result.row.id === detail.id) setDetail({ ...detail, values: result.row.values, intervals: result.intervals });
      else loadDetail(detail.id);
      setCanUndo(true);
    } catch (e) {
      toast.error(e);
    }
  };

  const deleteInterval = async (id: number) => {
    try {
      const result = await api.deleteInterval(id);
      storeRows([result.row]);
      if (detail) loadDetail(detail.id);
    } catch (e) {
      toast.error(e);
    }
  };

  const jumpInterval = (i: Interval) => {
    if (i.kind === "video") viewerRef.current?.seekFrame(i.start_frame ?? 0);
    else if (i.start_file_id) {
      const at = ids.indexOf(i.start_file_id);
      if (at >= 0) setIndex(at);
    }
  };

  // ---- navigation and keys ----------------------------------------------------------------
  const go = (delta: number) => setIndex((i) => Math.max(0, Math.min(ids.length - 1, i + delta)));

  const toggleSpecies = (key: string) => {
    const item = palette.items.find((i) => i.key === key);
    if (!item || project.readOnly) return;
    const ids_ = targets();
    if (!ids_.length) return;
    const row = ids_.length === 1 ? rowsRef.current.get(ids_[0]) ?? null : null;
    const on = row ? !isTrue(row.values[item.flag]) : true;
    change(speciesChange(palette, row, item.flag, on));
  };

  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (dialog || isTyping(e.target)) return;
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
      if (mod || e.altKey) return;
      switch (e.key) {
        case "ArrowRight": e.preventDefault(); go(1); break;
        case "ArrowLeft": e.preventDefault(); go(-1); break;
        case ".": viewerRef.current?.step(e.shiftKey ? 10 : 1); break;
        case ",": viewerRef.current?.step(e.shiftKey ? -10 : -1); break;
        case ">": viewerRef.current?.step(10); break;
        case "<": viewerRef.current?.step(-10); break;
        case " ": e.preventDefault(); viewerRef.current?.togglePlay(); break;
        case "s": case "S": markStart(); break;
        case "e": case "E": markEnd(); break;
        case "g": case "G": setShowGuides((v) => !v); break;
        case "b": case "B": setShowBoxes((v) => !v); break;
        case "a": case "A": setCompare(true); break;
        case "v": case "V": setView((v) => (v === "grid" ? "viewer" : "grid")); break;
        case "f": case "F": viewerRef.current?.fit(); break;
        case "d": case "D":
          if (currentRow) change({ DeleteFlag: isTrue(currentRow.values.DeleteFlag) ? "false" : "true" });
          break;
        case "?": setDialog("shortcuts"); break;
        case "Escape": setDrawing(null); setPending(null); break;
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
  const flagLabel = (label: string) => controls.find((c) => c.dataLabel === label)?.label ?? label;
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

  const folderTree = useMemo(() => {
    const nodes = new Map<string, number>();
    for (const f of project.folders) {
      const parts = f.path ? f.path.split("\\") : [];
      for (let i = 1; i <= parts.length; i++) {
        const key = parts.slice(0, i).join("\\");
        nodes.set(key, (nodes.get(key) ?? 0) + f.count);
      }
    }
    return [...nodes.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [project.folders]);

  const total = ids.length;
  const bulkCount = view === "grid" ? selection.size : 0;
  const frameTimes = videoInfo?.frameTimes ?? [];
  void rowsVersion;

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">{t("app.name")}</span>
        <span className="project" title={project.path}>{project.name}</span>
        <span className="spacer" />
        <span className={`tag${saving ? " saving" : ""}`}>
          {project.readOnly ? t("top.readOnly") : saving ? t("top.saving") : t("top.saved")}
        </span>
        <button className="icon-btn" disabled={!canUndo || project.readOnly} onClick={() => history(false)} title={`${t("top.undo")} (Ctrl+Z)`}>↶ {t("top.undo")}</button>
        <button className="icon-btn" disabled={!canRedo || project.readOnly} onClick={() => history(true)} title={`${t("top.redo")} (Ctrl+Shift+Z)`}>↷</button>
        <span className="lang">{info.serverMode ? t("top.server", { host: location.host }) : t("top.thisPc")}</span>
        <button className="icon-btn lang" onClick={() => setLang(lang === "ja" ? "en" : "ja")} aria-label={t("settings.language")}>
          {lang === "ja" ? "日本語 / EN" : "EN / 日本語"}
        </button>
        <button className="icon-btn" aria-haspopup="menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((v) => !v)}>
          {t("top.menu")} ▾
        </button>
        {menuOpen && (
          <div className="menu" role="menu" onMouseLeave={() => setMenuOpen(false)}>
            <button role="menuitem" disabled={saving > 0} onClick={() => { setMenuOpen(false); onOpenProject(); }}>{t("menu.open")}</button>
            <button role="menuitem" disabled={project.readOnly} onClick={() => { setMenuOpen(false); setDialog("recognitions"); }}>{t("menu.importRecognitions")}</button>
            <button role="menuitem" onClick={async () => {
              setMenuOpen(false);
              try { toast.push("success", t("csv.done", { path: (await api.exportCsv()).path })); } catch (e) { toast.error(e); }
            }}>{t("menu.exportCsv")}</button>
            <button role="menuitem" onClick={() => { setMenuOpen(false); setDialog("settings"); }}>{t("menu.settings")}</button>
            <button role="menuitem" onClick={() => { setMenuOpen(false); setDialog("shortcuts"); }}>{t("menu.shortcuts")}</button>
          </div>
        )}
      </header>
      {project.readOnly && <div className="ro-banner">! {t(project.readOnlyReason || "readOnly.requested")}</div>}

      <div className="panes">
        <aside className="pane left" aria-label={t("nav.folders")}>
          <div className="pane-head">{t("nav.folders")}</div>
          <div className="pane-body tree">
            <button aria-current={!filter.folder} onClick={() => setFilter({ ...filter, folder: undefined })}>
              {t("nav.all")} <span className="count">{project.total}</span>
            </button>
            {folderTree.map(([path, count]) => {
              const depth = path.split("\\").length - 1;
              return (
                <button key={path} aria-current={filter.folder === path} style={{ paddingLeft: 6 + depth * 14 }}
                        onClick={() => setFilter({ ...filter, folder: path })}>
                  {path.split("\\").pop()} <span className="count">{count}</span>
                </button>
              );
            })}
          </div>
          <div className="pane-head">{t("nav.filters")}<span className="sub">{t("filter.count", { count: total })}</span></div>
          <div className="pane-body">
            <input type="text" placeholder={t("filter.search")} aria-label={t("filter.search")} defaultValue={filter.text ?? ""}
                   onKeyDown={(e) => e.key === "Enter" && setFilter({ ...filter, text: (e.target as HTMLInputElement).value || undefined })}
                   onBlur={(e) => (e.target.value || undefined) !== filter.text && setFilter({ ...filter, text: e.target.value || undefined })} />
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {palette.items.map((i) => (
                <button key={i.flag} className="chip" aria-pressed={(filter.anyTrue ?? []).includes(i.flag)}
                        onClick={() => toggleAny(i.flag)}>{flagLabel(i.flag)}</button>
              ))}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
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
        </aside>

        <main className="center">
          <div className="toolbar">
            <button className="icon-btn" aria-pressed={view === "viewer"} onClick={() => setView("viewer")}>{t("view.viewer")}</button>
            <button className="icon-btn" aria-pressed={view === "grid"} onClick={() => setView("grid")}>{t("view.grid")}</button>
            <span className="sep" />
            <button className="icon-btn" onClick={() => go(-1)} aria-label="previous">←</button>
            <span className="pos">{t("viewer.position", { index: total ? index + 1 : 0, total })}</span>
            <button className="icon-btn" onClick={() => go(1)} aria-label="next">→</button>
            <span className="sep" />
            <button className="icon-btn" aria-pressed={showGuides} onClick={() => setShowGuides((v) => !v)}>{t("viewer.guides")}</button>
            {project.hasRecognitions && (
              <button className="icon-btn" aria-pressed={showBoxes} onClick={() => setShowBoxes((v) => !v)}>{t("viewer.bboxes")}</button>
            )}
            <button className="icon-btn" onClick={() => viewerRef.current?.fit()}>{t("viewer.fit")}</button>
            <span style={{ flex: 1 }} />
            {currentRow && <span className="pos" title={currentRow.values.RelativePath}>{currentRow.values.File} · {currentRow.values.DateTime}</span>}
          </div>
          {view === "grid" ? (
            <Grid mediaSession={mediaSession} ids={ids} rows={rowsRef.current} need={need} selection={selection} currentId={currentId}
                  onPick={pick} onOpen={(at) => { setIndex(at); setView("viewer"); }} speciesLabels={speciesLabels} />
          ) : (
            <>
              <Viewer ref={viewerRef} mediaSession={mediaSession} detail={detail}
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
                      videoInfo={videoInfo} intervals={detail?.intervals ?? []}
                      pendingStartFrame={pending?.kind === "video" && pending.fileId === detail?.id ? pending.frame ?? null : null}
                      onFrame={(f) => { frameRef.current = f; }} />
              {detail?.kind === "video" && (
                videoInfo?.available === false ? <div className="timeline">{t("video.noFfmpeg")}</div>
                : !videoInfo ? <div className="timeline">{t("video.loading")}</div>
                : <FrameTimeline viewerRef={viewerRef} frameTimes={frameTimes} exact={!!videoInfo.exactTimes}
                                 intervals={detail.intervals} fileId={detail.id}
                                 pendingStartFrame={pending?.kind === "video" && pending.fileId === detail.id ? pending.frame ?? null : null} />
              )}
            </>
          )}
        </main>

        <aside className="pane right" aria-label={t("data.title")}>
          <div className="pane-head">{t("data.title")}</div>
          <div className="pane-body">
            <DataPanel controls={controls} row={detail ? { id: detail.id, values: detail.values } : null}
                       palette={palette} locked={locked} readOnly={project.readOnly} bulkCount={bulkCount}
                       onChange={change} onCopyPrevious={copyPrevious} canCopyPrevious={index > 0} />
            {detail && bulkCount <= 1 && (
              <RestPanel kind={detail.kind} intervals={detail.intervals} pending={pending}
                         columns={project.settings.restColumns} onDelete={deleteInterval} onJump={jumpInterval}
                         onCancelPending={() => setPending(null)} readOnly={project.readOnly} frameTimes={frameTimes} />
            )}
            <ColorPanel value={color} onChange={setColor} hasFolderDefault={folderColor !== null} readOnly={project.readOnly}
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
            <GuidePanel guides={folderGuides.guides}
                        inheritedFrom={folderGuides.source !== null && folderGuides.source !== folder ? folderGuides.source : null}
                        drawing={drawing} onDraw={(s) => { setDrawing(s); setView("viewer"); }}
                        onChange={saveGuides} readOnly={project.readOnly} />
          </div>
        </aside>
      </div>

      {dialog === "settings" && (
        <SettingsDialog project={project} palette={palette} onClose={() => setDialog(null)}
                        onProject={(p) => { setProject(p); rowsRef.current.clear(); setRowsVersion((v) => v + 1); reloadIds(currentId); }} />
      )}
      {dialog === "shortcuts" && <ShortcutsDialog onClose={() => setDialog(null)} />}
      {dialog === "recognitions" && (
        <RecognitionDialog info={info} project={project} onClose={() => setDialog(null)}
                           onDone={async () => { setProject(await api.project()); loadDetail(currentId); }} />
      )}
    </div>
  );
}

/** Keeps its own frame state so the rest of the workspace does not re-render on every frame. */
function FrameTimeline({ viewerRef, frameTimes, exact, intervals, fileId, pendingStartFrame }: {
  viewerRef: React.RefObject<ViewerHandle>; frameTimes: number[]; exact: boolean; intervals: Interval[];
  fileId: number; pendingStartFrame: number | null;
}) {
  const [frame, setFrame] = useState(0);
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const f = viewerRef.current?.currentFrame() ?? 0;
      setFrame((old) => (old === f ? old : f));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [viewerRef]);
  return <Timeline frame={frame} total={frameTimes.length} frameTimes={frameTimes} intervals={intervals}
                   pendingStartFrame={pendingStartFrame} exact={exact} fileId={fileId}
                   onSeek={(f) => viewerRef.current?.seekFrame(f)} />;
}
