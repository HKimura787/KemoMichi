import { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";
import type { ColorAdjust, Guide, RestEvent, ShapeKind } from "../types";
import { NEUTRAL_COLOR } from "./Viewer";

export type TimeUnit = "seconds" | "frames";

/** "2.4 秒 → 11.2 秒" style summary of an event's entry and exit (design: 滞在). */
export function eventSpan(e: RestEvent, unit: TimeUnit, t: (k: string, p?: Record<string, string | number>) => string) {
  const at = (inside: boolean, seconds: string | null, frame: number | null, file: string | null, start: boolean) => {
    if (inside) return start ? t("event.fromStart") : t("event.toEnd");
    if (unit === "frames" && frame !== null) return t("event.frames", { frames: frame });
    if (seconds !== null) return t("rest.duration", { seconds });
    return file ?? "?";
  };
  const entry = at(e.start_inside, e.entrySeconds, e.start_frame, e.startFile, true);
  const exit = e.open ? t("event.open") : at(e.end_inside, e.exitSeconds, e.end_frame, e.endFile, false);
  return `${entry} → ${exit}`;
}

export function eventLength(e: RestEvent, unit: TimeUnit, t: (k: string, p?: Record<string, string | number>) => string) {
  if (e.open) return t("event.open");
  if (unit === "frames") {
    if (e.sameFile && e.start_frame !== null && e.end_frame !== null && !e.start_inside && !e.end_inside) {
      return t("event.frames", { frames: e.end_frame - e.start_frame });
    }
    return "—";
  }
  return e.durationSeconds !== null ? t("rest.duration", { seconds: e.durationSeconds }) : "—";
}

export function EventPanel({ fileId, sameFileRows, events, openEvents, speciesLabel, configured, readOnly, selected,
                            onSelect, onDelete, onJump, onEnd, onReopen, onSpecies, onIndividual, palette }: {
  fileId: number;
  sameFileRows: number[];
  events: RestEvent[];
  openEvents: RestEvent[];
  speciesLabel: (flag: string) => string;
  configured: boolean;
  readOnly: boolean;
  selected: number | null;
  onSelect: (e: RestEvent) => void;
  onDelete: (id: number) => void;
  onJump: (e: RestEvent, where: "start" | "end") => void;
  onEnd: (e: RestEvent, inside: boolean) => void;
  onReopen: (e: RestEvent) => void;
  onSpecies: (e: RestEvent, species: string) => void;
  onIndividual: (e: RestEvent, individual: string) => void;
  palette: { flag: string }[];
}) {
  const { t } = useI18n();
  const [unit, setUnit] = useState<TimeUnit>("seconds");
  const [menu, setMenu] = useState<number | null>(null);
  const mine = new Set([fileId, ...sameFileRows]);
  const here = events.filter((e) => mine.has(e.start_file_id) || (e.end_file_id !== null && mine.has(e.end_file_id)));
  const carried = openEvents.filter((e) => !mine.has(e.start_file_id) && !here.some((h) => h.id === e.id));
  const list = [...carried, ...here];

  return (
    <div className="grp" aria-labelledby="grp-stay">
      <div className="gt">
        <span id="grp-stay">{t("event.stay")}</span>
        <div className="seg sm" role="group" aria-label={t("event.unit")}>
          <button type="button" aria-pressed={unit === "seconds"} onClick={() => setUnit("seconds")}>{t("unit.seconds")}</button>
          <button type="button" aria-pressed={unit === "frames"} onClick={() => setUnit("frames")}>{t("unit.frames")}</button>
        </div>
      </div>
      {!configured && <p className="warn">! {t("event.noColumns")}</p>}
      <div className="evs">
        {list.length === 0 && <span className="note">{t("rest.none")}</span>}
        {list.map((e) => (
          <EventRow key={e.id} e={e} unit={unit} t={t} readOnly={readOnly} palette={palette} speciesLabel={speciesLabel}
                    current={selected === e.id} carried={!mine.has(e.start_file_id)}
                    menuOpen={menu === e.id} onMenu={(open) => setMenu(open ? e.id : null)}
                    onSelect={() => onSelect(e)} onDelete={() => onDelete(e.id)} onJump={(w) => onJump(e, w)}
                    onEnd={(inside) => onEnd(e, inside)} onReopen={() => onReopen(e)}
                    onSpecies={(s) => onSpecies(e, s)} onIndividual={(i) => onIndividual(e, i)} />
        ))}
      </div>
    </div>
  );
}

function EventRow({ e, unit, t, readOnly, palette, speciesLabel, current, carried, menuOpen, onMenu, onSelect, onDelete,
                    onJump, onEnd, onReopen, onSpecies, onIndividual }: {
  e: RestEvent; unit: TimeUnit; t: (k: string, p?: Record<string, string | number>) => string; readOnly: boolean;
  palette: { flag: string }[]; speciesLabel: (flag: string) => string; current: boolean; carried: boolean;
  menuOpen: boolean; onMenu: (open: boolean) => void; onSelect: () => void; onDelete: () => void;
  onJump: (where: "start" | "end") => void; onEnd: (inside: boolean) => void; onReopen: () => void;
  onSpecies: (species: string) => void; onIndividual: (individual: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menuOpen) return;
    const close = (ev: MouseEvent) => { if (!ref.current?.contains(ev.target as Node)) onMenu(false); };
    const esc = (ev: KeyboardEvent) => { if (ev.key === "Escape") onMenu(false); };
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", esc);
    return () => { window.removeEventListener("mousedown", close); window.removeEventListener("keydown", esc); };
  }, [menuOpen, onMenu]);
  const act = (fn: () => void) => () => { onMenu(false); fn(); };
  const name = speciesLabel(e.species) || "—";
  return (
    <div ref={ref} className={`ev${e.open ? " open" : ""}`} aria-current={current} data-testid={`event-${e.id}`}>
      <span className="id">#{e.individual || "?"}</span>
      <button type="button" className="body" onClick={onSelect} title={carried ? t("event.carriedOne", { file: e.startFile ?? "" }) : undefined}>
        <span className="nm">{carried ? "◀ " : ""}{name}</span>
        <span className="tm">{eventSpan(e, unit, t)}</span>
      </button>
      <span className="du">{eventLength(e, unit, t)}</span>
      <button type="button" className="more" aria-haspopup="menu" aria-expanded={menuOpen}
              aria-label={t("event.more", { id: e.individual })} onClick={() => onMenu(!menuOpen)}>⋯</button>
      {menuOpen && (
        <div className="evmenu" role="menu">
          <div className="row">
            <select value={e.species} disabled={readOnly} aria-label={t("data.species")}
                    onChange={(ev) => onSpecies(ev.target.value)}>
              <option value="">—</option>
              {palette.map((p) => <option key={p.flag} value={p.flag}>{speciesLabel(p.flag)}</option>)}
            </select>
            <input type="text" defaultValue={e.individual} key={`${e.id}-${e.individual}`} disabled={readOnly}
                   placeholder={t("event.individualPlaceholder")} aria-label={t("event.individual")} style={{ width: 64 }}
                   onBlur={(ev) => ev.target.value !== e.individual && onIndividual(ev.target.value)}
                   onKeyDown={(ev) => { if (ev.key === "Enter") (ev.target as HTMLInputElement).blur(); }} />
          </div>
          {e.open ? (
            <>
              <button role="menuitem" className="mi" disabled={readOnly} onClick={act(() => onEnd(false))}>{t("event.endHere")}</button>
              <button role="menuitem" className="mi" disabled={readOnly} onClick={act(() => onEnd(true))}>{t("event.endInside")}</button>
            </>
          ) : (
            <button role="menuitem" className="mi" disabled={readOnly} onClick={act(onReopen)}>{t("event.reopen")}</button>
          )}
          <button role="menuitem" className="mi" onClick={act(() => onJump("start"))}>{t("event.goStart")}</button>
          {!e.open && !e.sameFile && <button role="menuitem" className="mi" onClick={act(() => onJump("end"))}>{t("event.goEnd")}</button>}
          <button role="menuitem" className="mi danger" disabled={readOnly} onClick={act(onDelete)}>{t("rest.delete")}</button>
        </div>
      )}
    </div>
  );
}

export function ColorPanel({ value, onChange, onSaveFolder, onClearFolder, hasFolderDefault, readOnly, onClose }: {
  value: ColorAdjust;
  onChange: (c: ColorAdjust) => void;
  onSaveFolder: () => void;
  onClearFolder: () => void;
  hasFolderDefault: boolean;
  readOnly: boolean;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const slider = (key: "brightness" | "contrast" | "saturation" | "gamma", min: number, max: number) => (
    <div className="sl">
      <label htmlFor={`c-${key}`}>{t(`color.${key}`)}</label>
      <input id={`c-${key}`} type="range" min={min} max={max} step={0.05} value={value[key]}
             onChange={(e) => onChange({ ...value, [key]: Number(e.target.value) })}
             onDoubleClick={() => onChange({ ...value, [key]: 1 })} />
      <output htmlFor={`c-${key}`}>{value[key].toFixed(2)}</output>
    </div>
  );
  return (
    <div className="pop" role="dialog" aria-label={t("color.title")} style={{ top: 60 }}>
      <h3>{t("color.title")}<button className="btn text small" onClick={onClose} aria-label={t("open.cancel")}>✕</button></h3>
      {slider("brightness", 0.2, 3)}
      {slider("contrast", 0.2, 3)}
      {slider("saturation", 0, 3)}
      {slider("gamma", 0.3, 3)}
      <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input type="checkbox" checked={value.grayscale} onChange={(e) => onChange({ ...value, grayscale: e.target.checked })} />
        {t("color.grayscale")}
      </label>
      <div className="row">
        <button className="btn small" onClick={() => onChange(NEUTRAL_COLOR)}>{t("color.reset")}</button>
        <button className="btn small" disabled={readOnly} onClick={onSaveFolder}>{t("color.saveFolder")}</button>
        {hasFolderDefault && <button className="btn small" disabled={readOnly} onClick={onClearFolder}>{t("color.clearFolder")}</button>}
      </div>
    </div>
  );
}

const SHAPES: ShapeKind[] = ["line", "triangle", "rect", "polygon", "circle"];

export function GuidePanel({ guides, inheritedFrom, drawing, onDraw, onChange, readOnly, show, onShow, onClose }: {
  guides: Guide[];
  inheritedFrom: string | null;
  drawing: ShapeKind | null;
  onDraw: (shape: ShapeKind | null) => void;
  onChange: (guides: Guide[]) => void;
  readOnly: boolean;
  show: boolean;
  onShow: (show: boolean) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className="pop" role="dialog" aria-label={t("guide.title")} style={{ top: 112 }}>
      <h3>{t("guide.title")}<button className="btn text small" onClick={onClose} aria-label={t("open.cancel")}>✕</button></h3>
      <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input type="checkbox" checked={show} onChange={(e) => onShow(e.target.checked)} /> {t("guide.show")} <kbd>G</kbd>
      </label>
      {inheritedFrom !== null && <span className="note">{t("guide.inherited", { folder: inheritedFrom || "/" })}</span>}
      <div className="row">
        {SHAPES.map((s) => (
          <button key={s} className="chip" aria-pressed={drawing === s} disabled={readOnly}
                  onClick={() => onDraw(drawing === s ? null : s)}>{t(`guide.${s}`)}</button>
        ))}
        {drawing && <button className="btn text small" onClick={() => onDraw(null)}>{t("guide.cancel")}</button>}
      </div>
      {drawing && <span className="note">{t(drawing === "polygon" ? "guide.polygonHint" : "guide.drawing", { shape: t(`guide.${drawing}`) })}</span>}
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {guides.length === 0 && <span className="note">{t("guide.none")}</span>}
        {guides.map((g, i) => (
          <div key={g.id} className="gi">
            <input type="color" value={g.color} disabled={readOnly} aria-label={g.name}
                   onChange={(e) => onChange(guides.map((x, j) => (j === i ? { ...x, color: e.target.value } : x)))} />
            <input type="text" value={g.name} disabled={readOnly} aria-label={t(`guide.${g.shape}`)}
                   onChange={(e) => onChange(guides.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
            <select value={g.width} disabled={readOnly} aria-label="width"
                    onChange={(e) => onChange(guides.map((x, j) => (j === i ? { ...x, width: Number(e.target.value) } : x)))}>
              {[1, 2, 3, 4, 6].map((w) => <option key={w} value={w}>{w}px</option>)}
            </select>
            <button className="btn small" disabled={readOnly} onClick={() => onChange(guides.filter((_, j) => j !== i))}>
              {t("guide.delete")}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
