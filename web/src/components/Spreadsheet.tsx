import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { mediaUrl } from "../api";
import { useI18n } from "../i18n";
import type { Control, Row } from "../types";

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
            <th className="col-file">{t("control.File") || "File"}</th>
            <th className="col-folder">{t("control.RelativePath") || "Folder"}</th>
            <th className="col-datetime">{t("control.DateTime") || "DateTime"}</th>
            <th className="col-del">{t("control.DeleteFlag") || "Delete"}</th>
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
  const deleted = row?.values.DeleteFlag?.toLowerCase() === "true";
  const fileName = row?.values.File ?? "…";
  const folder = row?.values.RelativePath ?? "";
  const dateTime = row?.values.DateTime ?? "";
  const isVideo = /\.(mp4|avi|mov|asf)$/i.test(fileName);

  const handleCellChange = useCallback(
    (field: string, value: string) => {
      if (readOnly || locked.has(field)) return;
      void onWrite([id], { [field]: value });
    },
    [id, locked, onWrite, readOnly]
  );

  return (
    <tr
      className={`spreadsheet-row${isCurrent ? " selected" : ""}${deleted ? " deleted" : ""}`}
      onClick={onPick}
      onDoubleClick={onOpen}
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
          disabled={readOnly || locked.has("DateTime")}
          onCommit={(v) => handleCellChange("DateTime", v)}
        />
      </td>
      <td className="col-del text-center">
        <input
          type="checkbox"
          checked={deleted}
          disabled={readOnly || locked.has("DeleteFlag")}
          onChange={(e) => handleCellChange("DeleteFlag", String(e.target.checked))}
          aria-label={t("control.DeleteFlag") || "Delete"}
        />
      </td>
      {customControls.map((c) => {
        const val = row?.values[c.dataLabel] ?? "";
        const isLocked = readOnly || locked.has(c.dataLabel);

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

        if (c.type === "FixedChoice" || c.type === "MultiChoice") {
          if (c.choices && c.choices.length > 0) {
            return (
              <td key={c.id} className="col-custom">
                <CellSelect
                  value={val}
                  choices={c.choices}
                  includeEmpty={c.includeEmptyChoice}
                  disabled={isLocked}
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
  onCommit: (val: string) => void;
}

function CellInput({ value, type = "text", disabled, onCommit }: CellInputProps) {
  const [localVal, setLocalVal] = useState(value);
  const committedRef = useRef(value);

  useEffect(() => {
    setLocalVal(value);
    committedRef.current = value;
  }, [value]);

  const commit = useCallback(() => {
    if (localVal !== committedRef.current) {
      committedRef.current = localVal;
      onCommit(localVal);
    }
  }, [localVal, onCommit]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      commit();
      (e.target as HTMLInputElement).blur();
    } else if (e.key === "Escape") {
      setLocalVal(committedRef.current);
      (e.target as HTMLInputElement).blur();
    }
  };

  return (
    <input
      type={type}
      className="cell-input"
      value={localVal}
      disabled={disabled}
      onChange={(e) => setLocalVal(e.target.value)}
      onBlur={commit}
      onKeyDown={handleKeyDown}
    />
  );
}

interface CellSelectProps {
  value: string;
  choices: string[];
  includeEmpty: boolean;
  disabled?: boolean;
  onCommit: (val: string) => void;
}

function CellSelect({ value, choices, includeEmpty, disabled, onCommit }: CellSelectProps) {
  return (
    <select
      className="cell-select"
      value={value}
      disabled={disabled}
      onChange={(e) => onCommit(e.target.value)}
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
