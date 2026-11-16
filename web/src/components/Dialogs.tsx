import { useEffect, useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import type { EventColumns, Info, Palette, Project } from "../types";
import { Dialog, FileBrowser, useToast } from "../ui";

export function SettingsDialog({ project, palette, onClose, onProject }: {
  project: Project;
  palette: Palette;
  onClose: () => void;
  onProject: (p: Project) => void;
}) {
  const { t, lang, setLang } = useI18n();
  const toast = useToast();
  const [eventColumns, setEventColumns] = useState<EventColumns>({ ...project.eventColumns });
  // A Flag the stay events write to is not a species.
  const flags = project.controls.filter((c) => c.type === "Flag" && c.visible
    && c.dataLabel !== eventColumns.startInside && c.dataLabel !== eventColumns.endInside);
  const counters = project.controls.filter((c) => c.type === "Counter");
  const [items, setItems] = useState(() => {
    const byFlag = new Map(palette.items.map((i) => [i.flag, i]));
    return flags.map((f) => ({ flag: f.dataLabel, use: byFlag.has(f.dataLabel),
      counter: byFlag.get(f.dataLabel)?.counter ?? null, key: byFlag.get(f.dataLabel)?.key ?? "" }));
  });
  const [single, setSingle] = useState(palette.single);
  const [newName, setNewName] = useState("");
  const [withCount, setWithCount] = useState(true);
  const [busy, setBusy] = useState(false);
  const [threshold, setThreshold] = useState<number>(Number(project.settings.bboxThreshold ?? 0.2));
  const numberTargets = project.controls.filter((c) =>
    ["Note", "MultiLine", "DecimalAny", "DecimalPositive", "IntegerAny", "IntegerPositive"].includes(c.type));
  const textTargets = project.controls.filter((c) => ["Note", "MultiLine", "AlphaNumeric"].includes(c.type));
  const flagTargets = project.controls.filter((c) => c.type === "Flag");
  const speciesTargets = project.controls.filter((c) => ["Note", "MultiLine", "AlphaNumeric", "FixedChoice"].includes(c.type));

  // Only the rows on screen: a Flag chosen for stays above is no longer a species.
  const shown = (i: { flag: string }) => flags.some((f) => f.dataLabel === i.flag);
  const save = async () => {
    try {
      const newPalette: Palette = {
        items: items.filter((i) => i.use && shown(i)).map(({ flag, counter, key }) => ({ flag, counter, key })), single,
      };
      await api.setSetting("palette", newPalette);
      await api.setSetting("eventColumns", eventColumns);
      await api.setSetting("bboxThreshold", threshold);
      onProject(await api.project());
      onClose();
    } catch (e) {
      toast.error(e);
    }
  };

  const missingCounters = items.filter((i) => i.use && shown(i) && !i.counter);
  const addCounters = async () => {
    if (!window.confirm(t("settings.addCountersConfirm", { count: missingCounters.length }))) return;
    try {
      await api.setSetting("palette", { items: items.filter((i) => i.use && shown(i)).map(({ flag, counter, key }) => ({ flag, counter, key })), single });
      const result = await api.speciesCounters(missingCounters.map((i) => i.flag), lang === "ja" ? "の個数" : " count");
      onProject(result);
      const p = result.settings.palette;
      if (p) setItems((list) => list.map((i) => ({ ...i, counter: p.items.find((x) => x.flag === i.flag)?.counter ?? i.counter })));
      toast.push(result.templateUpdated ? "success" : "warning",
                 result.templateUpdated ? t("settings.countersAdded") : t("settings.countersNoTemplate"));
    } catch (e) {
      toast.error(e);
    }
  };

  const addSpecies = async () => {
    const name = newName.trim();
    if (!name || busy) return;
    setBusy(true);
    try {
      const result = await api.addSpecies(name, withCount, lang === "ja" ? "の個数" : " count");
      // The key comes from what is on screen: keys changed here and not saved yet count too.
      setItems((list) => {
        const rest = list.filter((i) => i.flag !== result.added.flag);
        const used = new Set(rest.filter((i) => i.use).map((i) => i.key));
        const key = "1234567890".split("").find((k) => !used.has(k)) ?? "";
        return [...rest, { flag: result.added.flag, use: true, counter: result.added.counter, key }];
      });
      onProject(result);
      setNewName("");
      toast.push(result.templateUpdated ? "success" : "warning",
                 result.templateUpdated ? t("settings.speciesAdded", { name }) : t("settings.countersNoTemplate"));
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(false);
    }
  };

  const eventKeys = ["speciesName", "individual", "startInside", "entry", "duration", "exitFile", "exit", "endInside"] as const;
  const known = new Set(project.controls.map((c) => c.dataLabel));
  const unsetEvents = eventKeys.filter((k) => !eventColumns[k] || !known.has(eventColumns[k]!));
  const addEventColumns = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const result = await api.addEventColumns([...unsetEvents], Object.fromEntries(unsetEvents.map((k) => [k, t(`settings.eventField.${k}`)])));
      setEventColumns((current) => ({ ...current, ...result.added }));
      onProject(result);
      toast.push(result.templateUpdated ? "success" : "warning",
                 result.templateUpdated ? t("settings.eventColumnsAdded", { count: Object.keys(result.added).length })
                   : t("settings.countersNoTemplate"));
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(false);
    }
  };

  const column = (key: "speciesName" | "individual" | "entry" | "exit" | "exitFile" | "startInside" | "endInside" | "duration") => {
    const targets = key === "speciesName" ? speciesTargets : key === "exitFile" || key === "individual" ? textTargets : key === "startInside" || key === "endInside" ? flagTargets : numberTargets;
    return (
      <div className="field">
        <label htmlFor={`ev-${key}`}>{t(`settings.event.${key}`)}</label>
        <select id={`ev-${key}`} value={eventColumns[key] ?? ""}
                onChange={(e) => setEventColumns({ ...eventColumns, [key]: e.target.value || null })}>
          <option value="">{t("settings.none")}</option>
          {targets.map((c) => <option key={c.dataLabel} value={c.dataLabel}>{c.label} ({c.dataLabel})</option>)}
        </select>
      </div>
    );
  };

  return (
    <Dialog title={t("settings.title")} onClose={onClose} wide
            actions={<>
              <button className="btn" onClick={onClose}>{t("dialog.cancel")}</button>
              <button className="btn main" disabled={project.readOnly} onClick={save}>{t("settings.save")}</button>
            </>}>
      <div className="field">
        <label htmlFor="lang">{t("settings.language")}</label>
        <select id="lang" value={lang} onChange={(e) => setLang(e.target.value as "ja" | "en")} style={{ width: 200 }}>
          <option value="ja">日本語</option>
          <option value="en">English</option>
        </select>
      </div>

      <div className="section-title">{t("settings.palette")}</div>
      <p className="note" style={{ margin: 0 }}>{t("settings.paletteLead")}</p>
      <table className="plain">
        <thead><tr><th>{t("settings.use")}</th><th>{t("settings.flag")}</th><th>{t("settings.counter")}</th><th>{t("settings.key")}</th></tr></thead>
        <tbody>
          {items.map((item, i) => {
            const flag = flags.find((f) => f.dataLabel === item.flag);
            if (!flag) return null;
            const update = (patch: Partial<typeof item>) => setItems(items.map((x, j) => (j === i ? { ...x, ...patch } : x)));
            return (
              <tr key={item.flag}>
                <td><input type="checkbox" checked={item.use} aria-label={flag.label} onChange={(e) => update({ use: e.target.checked })} /></td>
                <td>{flag.label} <span className="note">({flag.dataLabel})</span></td>
                <td>
                  <select value={item.counter ?? ""} onChange={(e) => update({ counter: e.target.value || null })} aria-label={t("settings.counter")}>
                    <option value="">{t("settings.none")}</option>
                    {counters.map((c) => <option key={c.dataLabel} value={c.dataLabel}>{c.label}</option>)}
                  </select>
                </td>
                <td>
                  <select value={item.key} onChange={(e) => update({ key: e.target.value })} aria-label={t("settings.key")} style={{ width: 72 }}>
                    <option value="">—</option>
                    {"1234567890".split("").map((k) => <option key={k} value={k}>{k}</option>)}
                  </select>
                </td>
              </tr>
            );
          })}
          {!items.some((i) => flags.some((f) => f.dataLabel === i.flag)) && (
            <tr><td colSpan={4} className="note">{t("settings.noSpecies")}</td></tr>
          )}
        </tbody>
      </table>
      <form className="add-row" onSubmit={(e) => { e.preventDefault(); addSpecies(); }}>
        <input type="text" value={newName} placeholder={t("settings.newSpecies")} aria-label={t("settings.newSpecies")}
               disabled={project.readOnly} onChange={(e) => setNewName(e.target.value)} />
        <label>
          <input type="checkbox" checked={withCount} disabled={project.readOnly}
                 onChange={(e) => setWithCount(e.target.checked)} />{t("settings.withCount")}
        </label>
        <button className="btn" type="submit" disabled={project.readOnly || busy || !newName.trim()}>{t("settings.addSpecies")}</button>
      </form>
      <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input type="checkbox" checked={single} onChange={(e) => setSingle(e.target.checked)} />{t("settings.single")}
      </label>
      {missingCounters.length > 0 && (
        <button className="btn" disabled={project.readOnly} onClick={addCounters} style={{ alignSelf: "flex-start" }}>
          {t("settings.addCounters")} ({missingCounters.length})
        </button>
      )}

      <div className="section-title">{t("settings.events")}</div>
      <p className="note" style={{ margin: 0 }}>{t("settings.eventsLead")}</p>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
        {column("speciesName")}{column("individual")}<span />
        {column("startInside")}{column("entry")}{column("duration")}
        {column("exitFile")}{column("exit")}{column("endInside")}
      </div>
      {unsetEvents.length > 0 && (
        <button className="btn" disabled={project.readOnly || busy} onClick={addEventColumns} style={{ alignSelf: "flex-start" }}>
          {t("settings.addEventColumns")} ({unsetEvents.length})
        </button>
      )}
      <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input type="checkbox" checked={eventColumns.writeSpecies}
               onChange={(e) => setEventColumns({ ...eventColumns, writeSpecies: e.target.checked })} />
        {t("settings.event.writeSpecies")}
      </label>
      <div className="field" style={{ maxWidth: 320 }}>
        <label htmlFor="ev-gap">{t("settings.event.gap")}</label>
        <input id="ev-gap" type="number" min={0} value={eventColumns.continuityGap}
               onChange={(e) => setEventColumns({ ...eventColumns, continuityGap: Number(e.target.value) || 0 })} />
      </div>

      {project.hasRecognitions && (
        <>
          <div className="section-title">{t("settings.bbox")}</div>
          <div className="slider">
            <span />
            <input type="range" min={0} max={1} step={0.05} value={threshold} aria-label={t("settings.bbox")}
                   onChange={(e) => setThreshold(Number(e.target.value))} />
            <output>{threshold.toFixed(2)}</output>
          </div>
        </>
      )}
    </Dialog>
  );
}

export function RecognitionDialog({ info, project, onClose, onDone }: {
  info: Info; project: Project; onClose: () => void; onDone: () => void;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      const { report } = await api.importRecognitions(selected);
      toast.push("success", t("rec.done", { images: report.imagesMatched, detections: report.detectionsStored }));
      if (report.unmatchedCount) toast.push("warning", t("rec.unmatched", { count: report.unmatchedCount }));
      if (report.trimmedLowConfidence) toast.push("info", t("rec.trimmed", { count: report.trimmedLowConfidence }));
      if (report.skippedVideoWithoutRate) toast.push("warning", t("rec.videoNoRate", { count: report.skippedVideoWithoutRate }));
      onDone();
      onClose();
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog title={t("rec.title")} onClose={onClose} wide
            actions={<>
              <button className="btn" onClick={onClose}>{t("dialog.cancel")}</button>
              <button className="btn main" disabled={!selected || busy || project.readOnly} onClick={run}>{t("dialog.ok")}</button>
            </>}>
      <p style={{ margin: 0 }}>{t("rec.lead")}</p>
      <FileBrowser start={project.root} kinds={["json"]} places={info.startFolders} selected={selected}
                   onSelect={(f) => setSelected(f.path)} />
    </Dialog>
  );
}

export function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const rows: [string, string][] = [
    ["← / →", t("sc.prevNext")],
    [", / .", t("sc.frame")],
    ["Space", t("sc.play")],
    ["[ / ]", t("sc.speed")],
    ["C", t("sc.capture")],
    ["1 … 9, 0", t("sc.species")],
    ["S / E", t("sc.se")],
    ["Shift+S / Shift+E", t("sc.seShift")],
    ["G", t("sc.guides")],
    ["B", t("sc.bboxes")],
    ["A", t("sc.compare")],
    ["V", t("sc.view")],
    ["F", t("sc.fit")],
    ["D", t("sc.delete")],
    ["Ctrl+Z / Ctrl+Shift+Z", t("sc.undo")],
    ["?", t("sc.help")],
  ];
  return (
    <Dialog title={t("shortcuts.title")} onClose={onClose}
            actions={<button className="btn main" onClick={onClose}>{t("settings.close")}</button>}>
      <table className="plain">
        <tbody>{rows.map(([k, v]) => <tr key={k}><td><kbd>{k}</kbd></td><td>{v}</td></tr>)}</tbody>
      </table>
    </Dialog>
  );
}

/** Pick one option with the mouse or a number key (1-9). */
export function ChoiceDialog({ title, options, onDone }: {
  title: string; options: { value: string; label: string }[]; onDone: (value: string | null) => void;
}) {
  const { t } = useI18n();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const n = Number(e.key);
      if (Number.isInteger(n) && n >= 1 && n <= options.length) {
        e.preventDefault();
        e.stopPropagation();
        onDone(options[n - 1].value);
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [options, onDone]);
  return (
    <Dialog title={title} onClose={() => onDone(null)}
            actions={<button className="btn" onClick={() => onDone(null)}>{t("dialog.cancel")}</button>}>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {options.map((o, i) => (
          <button key={o.value} className="btn" style={{ justifyContent: "flex-start" }} onClick={() => onDone(o.value)}>
            {i < 9 && <kbd>{i + 1}</kbd>} {o.label}
          </button>
        ))}
      </div>
    </Dialog>
  );
}
