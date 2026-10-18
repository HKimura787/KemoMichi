import { useI18n } from "../i18n";
import type { ColorAdjust, Guide, Interval, RestColumns, ShapeKind } from "../types";
import { formatTimecode, NEUTRAL_COLOR } from "./Viewer";

export interface PendingStart {
  kind: "video" | "sequence";
  fileId: number;
  frame?: number;
  label: string;
}

export function RestPanel({ kind, intervals, pending, columns, onDelete, onJump, onCancelPending, readOnly, frameTimes }: {
  kind: "image" | "video";
  intervals: Interval[];
  pending: PendingStart | null;
  columns: RestColumns | undefined;
  onDelete: (id: number) => void;
  onJump: (interval: Interval) => void;
  onCancelPending: () => void;
  readOnly: boolean;
  frameTimes: number[];
}) {
  const { t } = useI18n();
  const configured = columns && (columns.start || columns.end || columns.duration);
  return (
    <>
      <div className="section-title">{t("rest.title")}</div>
      <p className="note" style={{ margin: 0 }}>
        <kbd>S</kbd> / <kbd>E</kbd> — {kind === "video" ? t("rest.hintVideo") : t("rest.hintSequence")}
      </p>
      {!configured && <p className="note" style={{ margin: 0, color: "var(--km-warning)" }}>! {t("rest.noColumns")}</p>}
      {pending && (
        <div className="bulk" role="status">
          {t("rest.started", { at: pending.label })}{" "}
          <button className="btn text small" onClick={onCancelPending}>{t("rest.cancelStart")}</button>
        </div>
      )}
      <div className="intervals">
        {intervals.length === 0 && <span className="note">{t("rest.none")}</span>}
        {intervals.map((i, n) => (
          <div key={i.id} className="interval">
            <div>
              <span className="dur">{n + 1}. {t("rest.duration", { seconds: i.duration_seconds })}</span>
              <div className="note">
                {i.kind === "video"
                  ? `${t("rest.frames", { start: i.start_frame, end: i.end_frame })} (${formatTimecode(frameTimes[i.start_frame ?? 0] ?? 0)})`
                  : t("rest.images", { start: i.start_file_id, end: i.end_file_id })}
              </div>
            </div>
            <button className="btn small" onClick={() => onJump(i)}>{t("rest.jump")}</button>
            <button className="btn small" disabled={readOnly} onClick={() => onDelete(i.id)}>{t("rest.delete")}</button>
          </div>
        ))}
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
