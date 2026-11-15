import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { mediaUrl } from "../api";
import { useI18n } from "../i18n";
import type { Control, Row } from "../types";
import { useToast } from "../ui";

const ROW_HEIGHT = 34;

interface SpreadsheetProps {
  mediaSession: string;
  ids: number[];
  rows: Map<number, Row>;
  need: (ids: number[]) => void;
  currentId: number | null;
  onPick: (id: number, index: number) => void;
  onOpen: (index: number) => void;
  controls: Control[];
  locked: Set<string>;
  readOnly: boolean;
  onWrite: (fileIds: number[], values: Record<string, string>) => Promise<void>;
}

export function Spreadsheet({
  mediaSession,
  ids,
  rows,
  need,
  currentId,
  onPick,
  onOpen,
  controls,
  locked,
  readOnly,
  onWrite,
}: SpreadsheetProps) {
  const { t } = useI18n();
  const parentRef = useRef<HTMLDivElement>(null);
  const standardLabel = (type: string) => controls.find((control) => control.type === type)?.label ?? t(`template.type.${type}`);

  const customControls = useMemo(() => {
    return controls
      .filter((c) => !c.standard)
      .sort((a, b) => a.spreadsheetOrder - b.spreadsheetOrder);
  }, [controls]);

  const virtualizer = useVirtualizer({
    count: ids.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 20,
  });

  const items = virtualizer.getVirtualItems();

  useEffect(() => {
    if (!items.length) return;
    const first = items[0].index;
    const last = items[items.length - 1].index + 1;
    need(ids.slice(first, last));
  }, [items, ids, need]);

  useEffect(() => {
    if (currentId === null) return;
    const index = ids.indexOf(currentId);
    if (index >= 0) {
      virtualizer.scrollToIndex(index, { align: "auto" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentId]);

  const paddingTop = items.length > 0 ? items[0].start : 0;
  const paddingBottom =
    items.length > 0
      ? virtualizer.getTotalSize() - items[items.length - 1].end
      : 0;

  const totalCols = 6 + customControls.length;

  return (
    <div className="spreadsheet-container" ref={parentRef} role="region" aria-label={t("view.table")}>
      <table className="spreadsheet-table">
        <thead>
          <tr>
            <th className="col-num" title="#">#</th>
            <th className="col-thumb">{t("table.thumb")}</th>
            <th className="col-file">{standardLabel("File")}</th>
            <th className="col-folder">{standardLabel("RelativePath")}</th>
            <th className="col-datetime">{standardLabel("DateTime")}</th>
            <th className="col-del">{standardLabel("DeleteFlag")}</th>
            {customControls.map((c) => (
              <th
                key={c.id}
                className="col-custom"
                title={`${c.dataLabel} (${c.type})`}
                style={{ minWidth: Math.max(90, parseInt(c.width, 10) || 100) }}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ids.length === 0 ? (
            <tr>
              <td colSpan={totalCols} className="empty-cell">
                {t("table.empty")}
              </td>
            </tr>
          ) : (
            <>
              {paddingTop > 0 && (
                <tr className="virtual-spacer" aria-hidden="true">
                  <td colSpan={totalCols} style={{ height: `${paddingTop}px` }} />
                </tr>
              )}
              {items.map((vr) => {
                const id = ids[vr.index];
                const row = rows.get(id);
                const isCurrent = id === currentId;
                return (
                  <SpreadsheetRowItem
                    key={id}
                    index={vr.index}
                    id={id}
                    row={row}
                    isCurrent={isCurrent}
                    mediaSession={mediaSession}
                    customControls={customControls}
                    locked={locked}
                    readOnly={readOnly}
                    onPick={() => onPick(id, vr.index)}
                    onOpen={() => onOpen(vr.index)}
                    onWrite={onWrite}
                  />
                );
              })}
              {paddingBottom > 0 && (
                <tr className="virtual-spacer" aria-hidden="true">
                  <td colSpan={totalCols} style={{ height: `${paddingBottom}px` }} />
                </tr>
              )}
            </>
          )}
        </tbody>
      </table>
    </div>
  );
}

interface RowItemProps {
  index: number;
  id: number;
  row?: Row;
  isCurrent: boolean;
  mediaSession: string;
  customControls: Control[];
  locked: Set<string>;
  readOnly: boolean;
  onPick: () => void;
  onOpen: () => void;
  onWrite: (fileIds: number[], values: Record<string, string>) => Promise<void>;
}

const SpreadsheetRowItem = memo(function SpreadsheetRowItem({
  index,
  id,
  row,
  isCurrent,
  mediaSession,
  customControls,
  locked,
  readOnly,
  onPick,
  onOpen,
  onWrite,
}: RowItemProps) {
  const { t } = useI18n();
  const toast = useToast();
  const deleted = row?.values.DeleteFlag?.toLowerCase() === "true";
  const fileName = row?.values.File ?? "…";
  const folder = row?.values.RelativePath ?? "";
  const dateTime = row?.values.DateTime ?? "";
  const isVideo = /\.(mp4|avi|mov|asf)$/i.test(fileName);

  const handleCellChange = useCallback(
    async (field: string, value: string) => {
      if (readOnly || !row || locked.has(field)) return false;
      try {
        await onWrite([id], { [field]: value });
        return true;
      } catch (error) {
        toast.error(error);
        return false;
      }
    },
    [id, row, locked, onWrite, readOnly, toast.error]
  );

  return (
    <tr
      className={`spreadsheet-row${isCurrent ? " selected" : ""}${deleted ? " deleted" : ""}`}
      onClick={onPick}
      onDoubleClick={(event) => {
        if (!(event.target as HTMLElement).closest("input,select,textarea,button,details")) onOpen();
      }}
      style={{ height: `${ROW_HEIGHT}px` }}
    >
      <td className="col-num text-center">{index + 1}</td>
      <td className="col-thumb" title={t("table.doubleClickHint")}>
        <div className="thumb-wrap">
          <img
            src={mediaUrl(id, "thumb", mediaSession)}
            alt=""
            loading="lazy"
            draggable={false}
          />
          {isVideo && <span className="video-icon">▶</span>}
        </div>
      </td>
      <td className="col-file text-ellipsis" title={`${fileName} (${t("table.doubleClickHint")})`}>
        {fileName}
      </td>
      <td className="col-folder text-ellipsis" title={folder}>
        {folder}
      </td>
      <td className="col-datetime">
        <CellInput
          value={dateTime}
          disabled={readOnly || !row || locked.has("DateTime")}
          ariaLabel={`${t("template.type.DateTime")} (${index + 1})`}
          onCommit={(v) => handleCellChange("DateTime", v)}
        />
      </td>
      <td className="col-del text-center">
        <input
          type="checkbox"
          checked={deleted}
          disabled={readOnly || !row || locked.has("DeleteFlag")}
          onChange={(e) => handleCellChange("DeleteFlag", String(e.target.checked))}
          aria-label={t("data.deleteFlag")}
        />
      </td>
      {customControls.map((c) => {
        const val = row?.values[c.dataLabel] ?? "";
        const isLocked = readOnly || !row || locked.has(c.dataLabel);

        if (c.type === "Flag") {
          const checked = val.toLowerCase() === "true";
          return (
            <td key={c.id} className="col-custom text-center">
              <input
                type="checkbox"
                checked={checked}
                disabled={isLocked}
                onChange={(e) => handleCellChange(c.dataLabel, String(e.target.checked))}
                aria-label={c.label}
              />
            </td>
          );
        }

        if (c.type === "MultiChoice") {
          return <td key={c.id} className="col-custom">
            <CellMultiSelect value={val} choices={c.choices} disabled={isLocked} label={c.label}
                             onCommit={(v) => handleCellChange(c.dataLabel, v)} />
          </td>;
        }

        if (c.type === "FixedChoice") {
          if (c.choices && c.choices.length > 0) {
            return (
              <td key={c.id} className="col-custom">
                <CellSelect
                  value={val}
                  choices={c.choices}
                  includeEmpty={c.includeEmptyChoice}
                  disabled={isLocked}
                  label={`${c.label} (${index + 1})`}
                  onCommit={(v) => handleCellChange(c.dataLabel, v)}
                />
              </td>
            );
          }
        }

        const isNumeric = [
          "Counter",
          "IntegerAny",
          "IntegerPositive",
          "DecimalAny",
          "DecimalPositive",
        ].includes(c.type);

        return (
          <td key={c.id} className={`col-custom${isNumeric ? " text-right" : ""}`}>
            <CellInput
              value={val}
              type={isNumeric ? "number" : "text"}
              disabled={isLocked}
              ariaLabel={`${c.label} (${index + 1})`}
              multiline={c.type === "MultiLine"}
              onCommit={(v) => handleCellChange(c.dataLabel, v)}
            />
          </td>
        );
      })}
    </tr>
  );
});

interface CellInputProps {
  value: string;
  type?: "text" | "number";
  disabled?: boolean;
  ariaLabel?: string;
  multiline?: boolean;
  onCommit: (val: string) => Promise<boolean>;
}

function CellInput({ value, type = "text", disabled, onCommit, ariaLabel, multiline }: CellInputProps) {
  const [localVal, setLocalVal] = useState(value);
  const committedRef = useRef(value);
  const pending = useRef(false);
  const skipBlur = useRef(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLocalVal(value);
    committedRef.current = value;
  }, [value]);

  const commit = async () => {
    if (skipBlur.current) { skipBlur.current = false; return; }
    if (!pending.current && localVal !== committedRef.current) {
      pending.current = true;
      setSaving(true);
      try {
        if (!(await onCommit(localVal))) setLocalVal(committedRef.current);
      } finally {
        pending.current = false;
        setSaving(false);
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (!multiline || e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      (e.target as HTMLInputElement).blur();
    } else if (e.key === "Escape") {
      e.preventDefault();
      skipBlur.current = true;
      setLocalVal(committedRef.current);
      (e.target as HTMLInputElement).blur();
    }
  };

  const props = {
    "aria-label": ariaLabel,
    className: "cell-input", value: localVal, disabled: disabled || saving,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setLocalVal(e.target.value),
    onBlur: commit, onKeyDown: handleKeyDown,
  };
  return multiline ? <textarea {...props} rows={1} />
    : <input {...props} type="text" inputMode={type === "number" ? "decimal" : undefined} />;
}

interface CellSelectProps {
  value: string;
  choices: string[];
  includeEmpty: boolean;
  disabled?: boolean;
  label: string;
  onCommit: (val: string) => Promise<boolean>;
}

function CellSelect({ value, choices, includeEmpty, disabled, onCommit, label }: CellSelectProps) {
  const [saving, setSaving] = useState(false);
  return (
    <select
      className="cell-select"
      value={value}
      disabled={disabled || saving}
      aria-label={label}
      onChange={async (e) => {
        setSaving(true);
        try { await onCommit(e.target.value); }
        finally { setSaving(false); }
      }}
    >
      {includeEmpty && <option value="">—</option>}
      {choices.map((c) => (
        <option key={c} value={c}>
          {c}
        </option>
      ))}
    </select>
  );
}

function CellMultiSelect({ value, choices, disabled, label, onCommit }: {
  value: string; choices: string[]; disabled: boolean; label: string;
  onCommit: (value: string) => Promise<boolean>;
}) {
  const { t } = useI18n();
  const ref = useRef<HTMLDetailsElement>(null);
  const [saving, setSaving] = useState(false);
  const selected = new Set(value.split(",").filter(Boolean));
  useEffect(() => {
    const close = (event: PointerEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) ref.current.open = false;
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, []);
  return <details className="cell-multi" ref={ref} onKeyDown={(event) => {
    if (event.key === "Escape" && ref.current) { ref.current.open = false; event.stopPropagation(); }
  }}>
    <summary aria-label={label} aria-disabled={disabled}
             onClick={(event) => { if (disabled) event.preventDefault(); }}>{value || "—"}</summary>
    <div className="cell-multi-options" role="group" aria-label={label}>
      {choices.map((choice) => <label key={choice}>
        <input type="checkbox" checked={selected.has(choice)} disabled={disabled || saving}
               onChange={async (event) => {
                 const next = new Set(selected);
                 if (event.target.checked) next.add(choice); else next.delete(choice);
                 setSaving(true);
                 try { await onCommit(choices.filter((item) => next.has(item)).join(",")); }
                 finally { setSaving(false); }
               }} />{choice}
      </label>)}
      <button type="button" className="btn small" onClick={() => { if (ref.current) ref.current.open = false; }}>
        {t("settings.close")}
      </button>
    </div>
  </details>;
}
