import { useEffect, useState } from "react";
import { ApiError } from "../api";
import { useI18n } from "../i18n";
import type { Control, FileDetail, Palette, Row } from "../types";

const TRUE = "true";

export function isTrue(value: string | undefined): boolean {
  return (value ?? "").trim().toLowerCase() === TRUE;
}

/** Values to write when a species is switched on or off, or its count changes (plan §6.1). */
export function speciesChange(palette: Palette, row: Row | null, flag: string, on: boolean, count?: string) {
  const values: Record<string, string> = {};
  const item = palette.items.find((i) => i.flag === flag);
  values[flag] = on ? "true" : "false";
  if (item?.counter) {
    if (count !== undefined) values[item.counter] = count;
    else if (!on) values[item.counter] = "0";
    else if (!row || Number(row.values[item.counter] || 0) < 1) values[item.counter] = "1";
  }
  if (on && palette.single) {
    for (const other of palette.items) {
      if (other.flag === flag) continue;
      values[other.flag] = "false";
      if (other.counter) values[other.counter] = "0";
    }
  }
  return values;
}

export function DataPanel({ controls, row, detail, palette, locked, readOnly, bulkCount, onChange, onCopyPrevious, canCopyPrevious, onDuplicate }: {
  controls: Control[];
  row: Row | null;
  detail?: FileDetail | null;
  palette: Palette;
  locked: Set<string>;
  readOnly: boolean;
  bulkCount: number;
  onChange: (values: Record<string, string>, confirmText?: string) => Promise<void>;
  onCopyPrevious: () => void;
  canCopyPrevious: boolean;
  onDuplicate?: () => void;
}) {
  const { t } = useI18n();
  const byLabel = new Map(controls.map((c) => [c.dataLabel, c]));
  const paletteFlags = new Set(palette.items.map((i) => i.flag));
  const paletteCounters = new Set(palette.items.map((i) => i.counter).filter(Boolean) as string[]);
  const others = controls.filter((c) => !c.standard && c.visible && !paletteFlags.has(c.dataLabel) &&
                                        !paletteCounters.has(c.dataLabel));
  const bulk = bulkCount > 1;
  const disabled = readOnly || (!row && !bulk);
  const values = bulk ? {} as Record<string, string> : row?.values ?? {};

  const write = (label: string, value: string) => {
    const control = byLabel.get(label);
    const confirmText = bulk
      ? t("data.bulkConfirm", { count: bulkCount, field: control?.label ?? label, value })
      : undefined;
    return onChange({ [label]: value }, confirmText);
  };

  return (
    <>
      {bulk && <div className="bulk"><strong>{t("data.bulk", { count: bulkCount })}</strong><br />{t("data.bulkHint", { count: bulkCount })}</div>}
      {!bulk && row && (
        <div style={{ marginBottom: 12 }}>
          <div className="field" style={{ marginBottom: onDuplicate ? 6 : undefined }}>
            <span className="label">
              {t("data.file")}
              {detail?.recordTotal && detail.recordTotal > 1 ? (
                <span style={{ marginLeft: 6, fontWeight: "normal", fontSize: "0.85em", opacity: 0.85 }}>
                  {t("data.recordIndex", { current: detail.recordIndex, total: detail.recordTotal })}
                </span>
              ) : null}
            </span>
            <span className="path">{row.values.RelativePath ? `${row.values.RelativePath}\\` : ""}{row.values.File}</span>
          </div>
          {onDuplicate && (
            <button
              type="button"
              className="btn small"
              disabled={disabled}
              onClick={onDuplicate}
              title={t("data.duplicateHint")}
              style={{ width: "100%", justifyContent: "center" }}
            >
              ＋ {t("data.duplicate")}
            </button>
          )}
        </div>
      )}

      <div className="section-title">{t("data.species")}<span className="sub">{t("data.speciesHint")}</span></div>
      {palette.items.length === 0 && <p className="note">{t("data.noPalette")}</p>}
      <div className="palette">
        {palette.items.map((item) => {
          const control = byLabel.get(item.flag);
          if (!control) return null;
          const on = !bulk && isTrue(values[item.flag]);
          const count = item.counter && !bulk ? values[item.counter] : undefined;
          return (
            <button key={item.flag} className="sp" aria-pressed={on} disabled={disabled}
                    title={control.tooltip || control.label}
                    onClick={() => {
                      const change = speciesChange(palette, bulk ? null : row, item.flag, !on);
                      onChange(change, bulk ? t("data.bulkConfirm", { count: bulkCount, field: control.label, value: String(!on) }) : undefined);
                    }}>
              {control.label}
              <span className="meta">
                {item.key && <kbd>{item.key}</kbd>}{count !== undefined && count !== "0" && count !== "" ? ` × ${count}` : ""}
              </span>
            </button>
          );
        })}
      </div>
      {!bulk && row && (
        <div className="counts">
          {palette.items.filter((i) => i.counter && isTrue(values[i.flag])).map((item) => {
            const flag = byLabel.get(item.flag)!;
            const counter = item.counter!;
            const current = Number(values[counter] || 0);
            const set = (n: number) => onChange(speciesChange(palette, row, item.flag, n > 0, String(Math.max(0, n))));
            return (
              <div key={item.flag} className="count-row">
                <span>{flag.label} {t("data.count")}</span>
                <TextField value={values[counter] ?? ""} disabled={disabled} ariaLabel={`${flag.label} ${t("data.count")}`}
                           onCommit={(v) => set(Number(v || 0))} inputMode="numeric" />
                <button className="btn small" disabled={disabled} onClick={() => set(current - 1)} aria-label="-1">−</button>
                <button className="btn small" disabled={disabled} onClick={() => set(current + 1)} aria-label="+1">+</button>
              </div>
            );
          })}
        </div>
      )}

      <div className="section-title">{t("data.other")}</div>
      {!bulk && (
        <button className="btn small" disabled={disabled || !canCopyPrevious} onClick={onCopyPrevious}>
          {t("data.copyPrevious")}
        </button>
      )}
      {others.map((c) => (
        <ControlField key={c.dataLabel} control={c} value={values[c.dataLabel] ?? ""} bulk={bulk}
                      disabled={disabled} locked={locked.has(c.dataLabel)}
                      onCommit={(v) => write(c.dataLabel, v)} />
      ))}
      {byLabel.get("DateTime") && !bulk && row && (
        <ControlField control={byLabel.get("DateTime")!} value={values.DateTime ?? ""} disabled={disabled}
                      locked={false} bulk={false} onCommit={(v) => write("DateTime", v)} />
      )}
      {byLabel.get("DeleteFlag") && (
        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input type="checkbox" disabled={disabled} checked={!bulk && isTrue(values.DeleteFlag)}
                 onChange={(e) => write("DeleteFlag", e.target.checked ? "true" : "false")} />
          {t("data.deleteFlag")}
        </label>
      )}
    </>
  );
}

function ControlField({ control, value, disabled, locked, bulk, onCommit }: {
  control: Control; value: string; disabled: boolean; locked: boolean; bulk: boolean;
  onCommit: (value: string) => Promise<void>;
}) {
  const { t } = useI18n();
  const [error, setError] = useState<string | null>(null);
  const id = `f-${control.dataLabel}`;
  const commit = async (v: string) => {
    if (!bulk && v === value) return;
    try {
      setError(null);
      await onCommit(v);
    } catch (e) {
      if (e instanceof ApiError) setError(t(e.key, e.params));
      else throw e;
    }
  };
  const common = { id, disabled: disabled || locked };
  let input: JSX.Element;
  switch (control.type) {
    case "Flag":
      input = <input type="checkbox" {...common} checked={isTrue(value)} onChange={(e) => commit(e.target.checked ? "true" : "false")} />;
      break;
    case "FixedChoice":
      input = (
        <select {...common} value={value} onChange={(e) => commit(e.target.value)}>
          {(control.includeEmptyChoice || value === "" || bulk) && <option value="">{bulk ? "—" : ""}</option>}
          {control.choices.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      );
      break;
    case "MultiChoice": {
      const chosen = new Set(value.split(",").filter(Boolean));
      input = (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }} role="group" aria-labelledby={`${id}-l`}>
          {control.choices.map((c) => (
            <button key={c} className="chip" aria-pressed={chosen.has(c)} disabled={common.disabled}
                    onClick={() => {
                      const next = new Set(chosen);
                      if (next.has(c)) next.delete(c); else next.add(c);
                      commit(control.choices.filter((x) => next.has(x)).join(","));
                    }}>{c}</button>
          ))}
        </div>
      );
      break;
    }
    case "MultiLine":
      input = <TextField multiline {...common} value={value} onCommit={commit} />;
      break;
    case "Counter": case "IntegerAny": case "IntegerPositive":
      input = <TextField {...common} value={value} onCommit={commit} inputMode="numeric" />;
      break;
    case "DecimalAny": case "DecimalPositive":
      input = <TextField {...common} value={value} onCommit={commit} inputMode="decimal" />;
      break;
    default:
      input = <TextField {...common} value={value} onCommit={commit}
                         placeholder={control.type === "DateTime" || control.type === "DateTime_" ? "2026-04-01 12:34:56"
                           : control.type === "Date_" ? "2026-04-01" : control.type === "Time_" ? "12:34:56" : undefined} />;
  }
  return (
    <div className={`field${error ? " invalid" : ""}`} title={control.tooltip}>
      <label htmlFor={id} id={`${id}-l`}>{control.label}</label>
      {input}
      {locked && <span className="note">{t("data.locked")}</span>}
      {error && <span className="msg">✕ {error}</span>}
    </div>
  );
}

function TextField({ value, onCommit, multiline, disabled, id, inputMode, placeholder, ariaLabel }: {
  value: string; onCommit: (v: string) => void; multiline?: boolean; disabled?: boolean; id?: string;
  inputMode?: "numeric" | "decimal"; placeholder?: string; ariaLabel?: string;
}) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  const props = {
    id, disabled, value: draft, placeholder, "aria-label": ariaLabel,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setDraft(e.target.value),
    onBlur: () => draft !== value && onCommit(draft),
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !multiline) {
        (e.target as HTMLElement).blur();
      } else if (e.key === "Escape") {
        setDraft(value);
        (e.target as HTMLElement).blur();
      }
    },
  };
  return multiline ? <textarea {...props} /> : <input type="text" inputMode={inputMode} {...props} />;
}
