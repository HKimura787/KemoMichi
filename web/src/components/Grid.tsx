import { useEffect, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { mediaUrl } from "../api";
import { useI18n } from "../i18n";
import type { Row } from "../types";

const TILE = 200;
const GAP = 8;

export function Grid({ ids, rows, need, selection, currentId, onPick, onOpen, speciesLabels, duplicates }: {
  ids: number[];
  rows: Map<number, Row>;
  need: (ids: number[]) => void;
  selection: Set<number>;
  currentId: number | null;
  onPick: (id: number, index: number, e: React.MouseEvent) => void;
  onOpen: (index: number) => void;
  speciesLabels: (row: Row) => string[];
  duplicates: Record<string, number>;
}) {
  const { t } = useI18n();
  const parentRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);
  useEffect(() => {
    const el = parentRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setWidth(el.clientWidth - 16));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  const columns = Math.max(1, Math.floor((width + GAP) / (TILE + GAP)));
  const tile = Math.floor((width - GAP * (columns - 1)) / columns);
  const rowCount = Math.ceil(ids.length / columns);
  const virtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => parentRef.current,
    estimateSize: () => Math.round(tile * 0.75) + GAP,
    overscan: 3,
  });
  const items = virtualizer.getVirtualItems();

  useEffect(() => {
    if (!items.length) return;
    const first = items[0].index * columns;
    const last = Math.min(ids.length, (items[items.length - 1].index + 1) * columns);
    need(ids.slice(first, last));
  }, [items, columns, ids, need]);

  useEffect(() => {
    if (currentId === null) return;
    const index = ids.indexOf(currentId);
    if (index >= 0) virtualizer.scrollToIndex(Math.floor(index / columns), { align: "auto" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentId, columns]);

  return (
    <div className="grid" ref={parentRef} role="listbox" aria-multiselectable="true" aria-label={t("view.grid")}>
      <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
        {items.map((vr) => (
          <div key={vr.key} className="row" style={{ position: "absolute", top: vr.start, left: 0, right: 0 }}>
            {ids.slice(vr.index * columns, vr.index * columns + columns).map((id, i) => {
              const index = vr.index * columns + i;
              const row = rows.get(id);
              const selected = selection.has(id);
              const labels = row ? speciesLabels(row) : [];
              const deleted = row?.values.DeleteFlag?.toLowerCase() === "true";
              const isVideo = row ? /\.(mp4|avi|mov|asf)$/i.test(row.values.File ?? "") : false;
              const order = selected ? [...selection].indexOf(id) + 1 : 0;
              return (
                <div key={id} role="option" aria-selected={selected}
                     className={`thumb${currentId === id ? " current" : ""}`}
                     style={{ width: tile, height: Math.round(tile * 0.75) }}
                     title={row ? `${row.values.RelativePath}\\${row.values.File}  ${row.values.DateTime}` : ""}
                     onClick={(e) => onPick(id, index, e)} onDoubleClick={() => onOpen(index)}>
                  <img src={mediaUrl(id, "thumb")} alt={row?.values.File ?? ""} loading="lazy" draggable={false} />
                  {selected && <span className="badge">{order}</span>}
                  {deleted && <span className="del">{t("grid.deleted")}</span>}
                  {isVideo && <span className="video">▶</span>}
                  {duplicates[String(id)] !== undefined && <span className="dup">{t("grid.eventRow")}</span>}
                  <span className="labels">{labels.length ? labels.join(", ") : row?.values.File ?? "…"}</span>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
