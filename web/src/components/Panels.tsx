import { useI18n } from "../i18n";
import type { ColorAdjust, Guide, RestEvent, ShapeKind } from "../types";
import { NEUTRAL_COLOR } from "./Viewer";

export function EventPanel({ kind, fileId, events, openEvents, speciesLabel, configured, readOnly, onDelete, onJump,
                            onEnd, onReopen, onSpecies, palette }: {
  kind: "image" | "video";
  fileId: number;
  events: RestEvent[];
  openEvents: RestEvent[];
  speciesLabel: (flag: string) => string;
  configured: boolean;
  readOnly: boolean;
  onDelete: (id: number) => void;
  onJump: (e: RestEvent, where: "start" | "end") => void;
  onEnd: (e: RestEvent, inside: boolean) => void;
  onReopen: (e: RestEvent) => void;
  onSpecies: (e: RestEvent, species: string) => void;
  palette: { flag: string }[];
}) {
  const { t } = useI18n();
  const here = events.filter((e) => e.start_file_id === fileId || e.end_file_id === fileId);
  const elsewhereOpen = openEvents.filter((e) => e.start_file_id !== fileId);
  const point = (e: RestEvent, side: "start" | "end") => {
    if (side === "start") {
      if (e.start_inside) return t("event.insideAtStart", { file: e.startFile });
      return t("event.at", { file: e.startFile, seconds: e.entrySeconds ?? "?" });
    }
    if (e.open) return t("event.stillOpen");
    if (e.end_inside) return t("event.insideAtEnd", { file: e.endFile });
    return t("event.at", { file: e.endFile, seconds: e.exitSeconds ?? "?" });
  };
  const row = (e: RestEvent, n: number) => (
    <div key={e.id} className="interval" style={{ gridTemplateColumns: "1fr" }}>
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        <span className="dur">{n}.</span>
        <select value={e.species} disabled={readOnly} aria-label={t("data.species")} style={{ width: "auto", minHeight: 28 }}
                onChange={(ev) => onSpecies(e, ev.target.value)}>
          <option value="">—</option>
          {palette.map((p) => <option key={p.flag} value={p.flag}>{speciesLabel(p.flag)}</option>)}
        </select>
        {e.open ? <span className="chip" aria-pressed="true">{t("event.open")}</span>
          : <span className="dur">{e.durationSeconds !== null ? t("rest.duration", { seconds: e.durationSeconds })
            : e.elapsedSeconds !== null ? t("event.elapsed", { seconds: e.elapsedSeconds }) : ""}</span>}
      </div>
      <div className="note">{t("event.entry")}: {point(e, "start")}</div>
      <div className="note">{t("event.exit")}: {point(e, "end")}</div>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
        {e.open ? (
          <>
            <button className="btn small" disabled={readOnly} onClick={() => onEnd(e, false)}>{t("event.endHere")}</button>
            <button className="btn small" disabled={readOnly} onClick={() => onEnd(e, true)}>{t("event.endInside")}</button>
          </>
        ) : (
          <button className="btn small" disabled={readOnly} onClick={() => onReopen(e)}>{t("event.reopen")}</button>
        )}
        <button className="btn small" onClick={() => onJump(e, "start")}>{t("event.goStart")}</button>
        {!e.open && !e.sameFile && <button className="btn small" onClick={() => onJump(e, "end")}>{t("event.goEnd")}</button>}
        <button className="btn small" disabled={readOnly} onClick={() => onDelete(e.id)}>{t("rest.delete")}</button>
      </div>
    </div>
  );
  return (
    <>
      <div className="section-title">{t("event.title")}</div>
      <p className="note" style={{ margin: 0 }}>
        <kbd>S</kbd> {kind === "video" ? t("event.keyS") : t("event.keySImage")}・<kbd>Shift+S</kbd> {t("event.keyShiftS")}<br />
        <kbd>E</kbd> {kind === "video" ? t("event.keyE") : t("event.keyEImage")}・<kbd>Shift+E</kbd> {t("event.keyShiftE")}
      </p>
      {!configured && <p className="note" style={{ margin: 0, color: "var(--km-warning)" }}>! {t("event.noColumns")}</p>}
      {elsewhereOpen.length > 0 && (
        <div className="bulk" role="status">
          <strong>{t("event.carried", { count: elsewhereOpen.length })}</strong>
          <div className="intervals">{elsewhereOpen.map((e, i) => row(e, i + 1))}</div>
        </div>
      )}
      <div className="intervals">
        {here.length === 0 && <span className="note">{t("rest.none")}</span>}
        {here.map((e, i) => row(e, i + 1))}
      </div>
    </>
  );
}

export function ColorPanel({ value, onChange, onSaveFolder, onClearFolder, hasFolderDefault, readOnly }: {
  value: ColorAdjust;
  onChange: (c: ColorAdjust) => void;
  onSaveFolder: () => void;
  onClearFolder: () => void;
  hasFolderDefault: boolean;
  readOnly: boolean;
}) {
  const { t } = useI18n();
  const slider = (key: "brightness" | "contrast" | "saturation" | "gamma", min: number, max: number) => (
    <div className="slider">
      <label htmlFor={`c-${key}`}>{t(`color.${key}`)}</label>
      <input id={`c-${key}`} type="range" min={min} max={max} step={0.05} value={value[key]}
             onChange={(e) => onChange({ ...value, [key]: Number(e.target.value) })}
             onDoubleClick={() => onChange({ ...value, [key]: 1 })} />
      <output htmlFor={`c-${key}`}>{value[key].toFixed(2)}</output>
    </div>
  );
  return (
    <details>
      <summary className="section-title" style={{ cursor: "pointer" }}>{t("color.title")}</summary>
      <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 6 }}>
        {slider("brightness", 0.2, 3)}
        {slider("contrast", 0.2, 3)}
        {slider("saturation", 0, 3)}
        {slider("gamma", 0.3, 3)}
        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input type="checkbox" checked={value.grayscale} onChange={(e) => onChange({ ...value, grayscale: e.target.checked })} />
          {t("color.grayscale")}
        </label>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button className="btn small" onClick={() => onChange(NEUTRAL_COLOR)}>{t("color.reset")}</button>
          <button className="btn small" disabled={readOnly} onClick={onSaveFolder}>{t("color.saveFolder")}</button>
          {hasFolderDefault && <button className="btn small" disabled={readOnly} onClick={onClearFolder}>{t("color.clearFolder")}</button>}
        </div>
      </div>
    </details>
  );
}

const SHAPES: ShapeKind[] = ["line", "triangle", "rect", "polygon", "circle"];

export function GuidePanel({ guides, inheritedFrom, drawing, onDraw, onChange, readOnly }: {
  guides: Guide[];
  inheritedFrom: string | null;
  drawing: ShapeKind | null;
  onDraw: (shape: ShapeKind | null) => void;
  onChange: (guides: Guide[]) => void;
  readOnly: boolean;
}) {
  const { t } = useI18n();
  return (
    <details open={guides.length > 0 || drawing !== null}>
      <summary className="section-title" style={{ cursor: "pointer" }}>{t("guide.title")}</summary>
      <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 6 }}>
        {inheritedFrom !== null && <span className="note">{t("guide.inherited", { folder: inheritedFrom || "/" })}</span>}
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {SHAPES.map((s) => (
            <button key={s} className="chip" aria-pressed={drawing === s} disabled={readOnly}
                    onClick={() => onDraw(drawing === s ? null : s)}>{t(`guide.${s}`)}</button>
          ))}
          {drawing && <button className="btn text small" onClick={() => onDraw(null)}>{t("guide.cancel")}</button>}
        </div>
        <div className="guide-list">
          {guides.length === 0 && <span className="note">{t("guide.none")}</span>}
          {guides.map((g, i) => (
            <div key={g.id} className="guide-item">
              <input type="color" value={g.color} disabled={readOnly} aria-label={g.name}
                     onChange={(e) => onChange(guides.map((x, j) => (j === i ? { ...x, color: e.target.value } : x)))} />
              <input type="text" value={g.name} disabled={readOnly} aria-label={t(`guide.${g.shape}`)}
                     onChange={(e) => onChange(guides.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
              <select value={g.width} disabled={readOnly} aria-label="width"
                      onChange={(e) => onChange(guides.map((x, j) => (j === i ? { ...x, width: Number(e.target.value) } : x)))}
                      style={{ width: 64 }}>
                {[1, 2, 3, 4, 6].map((w) => <option key={w} value={w}>{w}px</option>)}
              </select>
              <button className="btn small" disabled={readOnly} onClick={() => onChange(guides.filter((_, j) => j !== i))}>
                {t("guide.delete")}
              </button>
            </div>
          ))}
        </div>
      </div>
    </details>
  );
}
