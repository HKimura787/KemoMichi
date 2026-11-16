import { useVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "../i18n";
import { ancestors, buildTree, folderOf, keyAction, rowDomId, visibleRows, type TreeData } from "../tree";

const ROW = 26;

function loadExpanded(storageKey: string): Set<string> {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) ?? "[]");
    return new Set(Array.isArray(saved) ? saved.filter((p) => typeof p === "string") : []);
  } catch {
    return new Set();
  }
}

/**
 * Folders and their files, as in an editor's explorer: a folder opens and closes, a file is
 * shown when picked, and the file on screen stays marked and in view.
 */
export function FileTree({ data, currentId, stateOf, storageKey, filterFolder, onFilterFolder, onOpen }: {
  data: TreeData | null;
  currentId: number | null;
  /** Fresher state bits for a file the page has loaded (see tree.ts). */
  stateOf: (id: number, state: number) => number;
  storageKey: string;
  filterFolder?: string;
  onFilterFolder: (path: string | undefined) => void;
  /** `activate`: Enter or a double click, which also brings up the viewer. */
  onOpen: (id: number, activate: boolean) => void;
}) {
  const { t } = useI18n();
  const scroller = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(() => loadExpanded(storageKey));
  const [cursor, setCursor] = useState<string | null>(null);
  const revealed = useRef<number | null>(null);
  const scrollTo = useRef<string | null>(null);

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify([...expanded]));
    } catch {
      /* storage unavailable: the tree still works, it only forgets */
    }
  }, [expanded, storageKey]);

  // Follow the file on screen: open the folders above it, once per file, and scroll to it.
  useEffect(() => {
    if (!data || currentId === null || revealed.current === currentId) return;
    const path = folderOf(data, currentId);
    if (path === null) return;
    revealed.current = currentId;
    scrollTo.current = "f:" + currentId;
    setCursor("f:" + currentId);
    const missing = ancestors(path).filter((p) => !expanded.has(p));
    if (missing.length) setExpanded((old) => new Set([...old, ...missing]));
  }, [data, currentId, expanded]);

  const nodes = useMemo(() => (data ? buildTree(data, stateOf) : null), [data, stateOf]);
  const rows = useMemo(
    () => (data && nodes ? visibleRows(data, nodes, expanded, currentId, stateOf) : []),
    [data, nodes, expanded, currentId, stateOf]);

  const virtualizer = useVirtualizer({
    count: rows.length, getScrollElement: () => scroller.current, estimateSize: () => ROW, overscan: 12,
  });

  useEffect(() => {
    if (!scrollTo.current) return;
    const at = rows.findIndex((r) => r.key === scrollTo.current);
    if (at < 0) return;
    scrollTo.current = null;
    virtualizer.scrollToIndex(at, { align: "auto" });
  }, [rows, virtualizer]);

  const toggle = (path: string, open: boolean) => setExpanded((old) => {
    const next = new Set(old);
    if (open) next.add(path);
    else next.delete(path);
    return next;
  });

  const cursorAt = Math.max(0, rows.findIndex((r) => r.key === cursor));
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const action = keyAction(rows, cursorAt, e.key, e.shiftKey);
    const handled = ["ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight", "Home", "End", "Enter", " "].includes(e.key);
    if (!handled) return;
    // The workspace's own arrow keys (previous / next file) must not also fire.
    e.preventDefault();
    e.stopPropagation();
    if (!action) return;
    if (action.type === "move") {
      setCursor(action.key);
      scrollTo.current = action.key;
      virtualizer.scrollToIndex(rows.findIndex((r) => r.key === action.key), { align: "auto" });
    } else if (action.type === "toggle") toggle(action.path, action.open);
    else if (action.type === "only") onFilterFolder(filterFolder === action.path ? undefined : action.path);
    else onOpen(action.id, true);
  };

  if (!data) return <div className="ftree" aria-busy="true" />;
  if (!rows.length) return <div className="ftree"><p className="ftree-empty">{t("tree.empty")}</p></div>;

  const activeKey = rows[cursorAt]?.key;
  const items = virtualizer.getVirtualItems();
  // Only rows near the view are in the page; point at the cursor's row only while it is one of them.
  const activeShown = items.some((item) => rows[item.index]?.key === activeKey);
  return (
    <div className="ftree" ref={scroller} role="tree" tabIndex={0} aria-label={t("nav.files")}
         aria-activedescendant={activeKey && activeShown ? rowDomId(activeKey) : undefined} onKeyDown={onKeyDown}>
      <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
        {items.map((item) => {
          const row = rows[item.index];
          const style = { transform: `translateY(${item.start}px)`, height: ROW, paddingLeft: 6 + row.depth * 14 };
          const cls = "trow" + (row.key === activeKey ? " cursor" : "");
          if (row.kind === "folder") {
            const narrowed = filterFolder === row.path;
            const count = t("tree.folderCount", { entered: row.entered, total: row.total });
            const here = row.hasCurrent && !row.open ? " · " + t("tree.holdsCurrent") : "";
            return (
              <div key={row.key} id={rowDomId(row.key)} role="treeitem" aria-level={row.depth + 1} aria-expanded={row.open}
                   aria-posinset={row.pos} aria-setsize={row.size} aria-keyshortcuts="Shift+Enter"
                   aria-label={`${row.name} (${count})${here}`} className={cls + " dir" + (row.hasCurrent && !row.open ? " has-current" : "")}
                   style={style} title={row.path}
                   onClick={() => { setCursor(row.key); toggle(row.path, !row.open); }}>
                <span className="tw" aria-hidden="true">{row.open ? "▾" : "▸"}</span>
                <span className="nm">{row.name}</span>
                <button type="button" className={"only" + (narrowed ? " on" : "")} aria-pressed={narrowed} tabIndex={-1}
                        aria-label={t("tree.onlyFolder", { name: row.name })} title={t("tree.onlyFolder", { name: row.name }) + " (Shift+Enter)"}
                        onClick={(e) => { e.stopPropagation(); onFilterFolder(narrowed ? undefined : row.path); }}>
                  <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true"><path d="M1.5 2.5h13L9.5 8.6v4.4l-3 1.5V8.6z" fill="currentColor" /></svg>
                </button>
                <span className="n" title={count}>
                  {row.entered}/{row.total}
                </span>
              </div>
            );
          }
          const state = row.deleted ? t("tree.deleted") : row.entered ? t("tree.entered") : t("tree.unentered");
          return (
            <div key={row.key} id={rowDomId(row.key)} role="treeitem" aria-level={row.depth + 1}
                 aria-posinset={row.pos} aria-setsize={row.size}
                 aria-current={row.current ? "true" : undefined} aria-selected={row.current}
                 aria-label={`${row.name} (${state})`}
                 className={cls + " file" + (row.current ? " current" : "") + (row.deleted ? " deleted" : "")}
                 style={style} title={`${row.name} · ${state}`}
                 onClick={() => { setCursor(row.key); onOpen(row.id, false); }}
                 onDoubleClick={() => onOpen(row.id, true)}>
              <span className={"dot" + (row.entered ? " on" : "")} aria-hidden="true" />
              <span className="nm">{row.name}</span>
              {row.records > 1 && <span className="rec" title={t("tree.records", { count: row.records })}>×{row.records}</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
