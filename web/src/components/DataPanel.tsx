import { useEffect, useState } from "react";
import { ApiError } from "../api";
import { useI18n } from "../i18n";
import type { Control, Palette, Row } from "../types";

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

export function DataPanel({ controls, row, palette, locked, readOnly, bulkCount, onChange, onCopyPrevious, canCopyPrevious,
                           afterSpecies, onNext, canNext }: {
  controls: Control[];
  row: Row | null;
  palette: Palette;
  locked: Set<string>;
  readOnly: boolean;
  bulkCount: number;
  onChange: (values: Record<string, string>, confirmText?: string) => Promise<void>;
  onCopyPrevious: () => void;
  canCopyPrevious: boolean;
  afterSpecies?: React.ReactNode;
  onNext?: () => void;
  canNext?: boolean;
}) {
  const { t } = useI18n();
  const byLabel = new Map(controls.map((c) => [c.dataLabel, c]));
  const paletteItems = palette.items.filter((item) => {
    const control = byLabel.get(item.flag);
    return control?.type === "Flag" && control.visible && !locked.has(item.flag);
  }).map((item) => ({ ...item, counter: item.counter && byLabel.get(item.counter)?.type === "Counter" &&
    !locked.has(item.counter) ? item.counter : null }));
  const inputPalette = { ...palette, items: paletteItems };
  const paletteFlags = new Set(paletteItems.map((i) => i.flag));
  const counterOwners = new Map<string, string>();
  for (const item of paletteItems) {
    if (item.counter) counterOwners.set(item.counter, item.flag);
  }
  // A palette association must never hide a template's input field.
  const others = controls.filter((c) => !c.standard && c.visible && !paletteFlags.has(c.dataLabel));
  const bulk = bulkCount > 1;
  const disabled = readOnly || (!row && !bulk);
  const values = bulk ? {} as Record<string, string> : row?.values ?? {};

  const write = (label: string, value: string) => {
    const control = byLabel.get(label);
    const confirmText = bulk
      ? t("data.bulkConfirm", { count: bulkCount, field: control?.label ?? label, value })
      : undefined;
    const flag = counterOwners.get(label);
    return onChange(flag ? speciesChange(inputPalette, bulk ? null : row, flag, Number(value) > 0, value)
      : { [label]: value }, confirmText);
  };
  const toggle = (flag: string, label: string, on: boolean) => {
    const change = speciesChange(inputPalette, bulk ? null : row, flag, on);
    onChange(change, bulk ? t("data.bulkConfirm", { count: bulkCount, field: label, value: String(on) }) : undefined);
  };
  const dateTime = byLabel.get("DateTime");

  return (
    <>
      <div className="scroll">
        {bulk && <div className="grp"><div className="bulk"><strong>{t("data.bulk", { count: bulkCount })}</strong><br />{t("data.bulkHint", { count: bulkCount })}</div></div>}
        <div className="grp">
          <div className="gt">{t("data.species")}</div>
          {paletteItems.length === 0 && <p className="note">{t("data.noPalette")}</p>}
          <div className="pal">
            {paletteItems.map((item) => {
              const control = byLabel.get(item.flag);
              if (!control) return null;
              const on = !bulk && isTrue(values[item.flag]);
              const count = item.counter && !bulk ? Number(values[item.counter] || 0) : null;
              return (
                <div key={item.flag} className={`spc${on ? " on" : ""}`} title={control.tooltip || control.label}>
                  <button type="button" className="nm" aria-pressed={on} disabled={disabled}
                          onClick={() => toggle(item.flag, control.label, !on)}>
                    {item.key && <kbd>{item.key}</kbd>}<span>{control.label}</span>
                  </button>
                  {on && count !== null && item.counter && (
                    <div className="st">
                      <button type="button" disabled={disabled} aria-label={`${control.label} −`}
                              onClick={() => write(item.counter!, String(Math.max(0, count - 1)))}>−</button>
                      <output aria-label={byLabel.get(item.counter)?.label}>{count}</output>
                      <button type="button" disabled={disabled} aria-label={`${control.label} ＋`}
                              onClick={() => write(item.counter!, String(count + 1))}>+</button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
        {afterSpecies}
        <div className="grp">
          <div className="gt">
            {t("data.fields")}
            {!bulk && (
              <button type="button" className="btn sm" disabled={disabled || !canCopyPrevious} onClick={onCopyPrevious}>
                {t("data.samePrev")}
              </button>
            )}
          </div>
          <div className="fg">
            {others.map((c) => (
              <ControlField key={c.dataLabel} control={c} value={values[c.dataLabel] ?? ""} bulk={bulk}
                            disabled={disabled} locked={locked.has(c.dataLabel)}
                            stepButtons={!bulk && counterOwners.has(c.dataLabel)}
                            onCommit={(v) => write(c.dataLabel, v)} />
            ))}
            {dateTime && !bulk && row && (
              <ControlField control={dateTime} value={values.DateTime ?? ""} disabled={disabled}
                            locked={false} bulk={false} onCommit={(v) => write("DateTime", v)} />
            )}
          </div>
        </div>
      </div>
      <div className="foot">
        {byLabel.get("DeleteFlag") && (
          <label>
            <input type="checkbox" disabled={disabled} checked={!bulk && isTrue(values.DeleteFlag)}
                   onChange={(e) => write("DeleteFlag", e.target.checked ? "true" : "false")} />
            {t("data.deleteFlag")}
          </label>
        )}
        <span className="spacer" />
        {onNext && <button type="button" className="btn main" disabled={!canNext} onClick={onNext}>{t("data.next")} →</button>}
      </div>
    </>
  );
}

function ControlField({ control, value, disabled, locked, bulk, stepButtons, onCommit }: {
  control: Control; value: string; disabled: boolean; locked: boolean; bulk: boolean;
  stepButtons?: boolean;
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
  const wide = control.type === "MultiLine" || control.type === "MultiChoice" || !!stepButtons;
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
    <div className={`field${error ? " invalid" : ""}${locked ? " auto" : ""}${wide ? " w" : ""}`} title={control.tooltip}>
      <label htmlFor={id} id={`${id}-l`}>{control.label}</label>
      {stepButtons ? <div className="counter-input">
        {input}
        <button className="btn small" disabled={common.disabled} aria-label={`${control.label} -1`}
                onClick={() => commit(String(Math.max(0, Number(value || 0) - 1)))}>−</button>
        <button className="btn small" disabled={common.disabled} aria-label={`${control.label} +1`}
                onClick={() => commit(String(Math.max(0, Number(value || 0) + 1)))}>+</button>
      </div> : input}
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
