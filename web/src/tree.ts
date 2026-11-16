// The file tree of the left pane, as plain data: the server's listing (api.tree) turned into
// folder nodes, and those into the rows on screen. No React here, so the rules are testable.

/** [file id, index into folders, file name, state bits, how many records the file has]. */
export type TreeFile = [id: number, folder: number, name: string, state: number, records: number];
export interface TreeData { folders: string[]; files: TreeFile[] }

export const ENTERED = 1;
export const DELETED = 2;
const SEP = "\\";

export interface FolderNode {
  path: string;          // "" is the root
  name: string;
  depth: number;         // root = -1, top-level folders = 0
  folders: string[];     // child folder paths, in the order the listing first reaches them
  files: number[];       // indices into TreeData.files, in the server's order
  total: number;         // files in this folder and below
  entered: number;       // of those, how many have a species
}

export type TreeRow =
  | { kind: "folder"; key: string; path: string; name: string; depth: number; pos: number; size: number;
      total: number; entered: number; open: boolean; hasCurrent: boolean }
  | { kind: "file"; key: string; id: number; name: string; depth: number; pos: number; size: number;
      entered: boolean; deleted: boolean; records: number; current: boolean };

/** "A\\B\\C" → ["A", "A\\B", "A\\B\\C"]; the root ("") has none. */
export function ancestors(path: string): string[] {
  const parts = path ? path.split(SEP) : [];
  return parts.map((_, i) => parts.slice(0, i + 1).join(SEP));
}

/**
 * Folder nodes by path. `stateOf` may replace a file's state bits with fresher ones (a row the
 * page has already loaded and edited); by default the server's bits count.
 */
export function buildTree(data: TreeData, stateOf: (id: number, state: number) => number = (_, s) => s): Map<string, FolderNode> {
  const nodes = new Map<string, FolderNode>();
  const node = (path: string): FolderNode => {
    let found = nodes.get(path);
    if (!found) {
      const parts = path ? path.split(SEP) : [];
      found = { path, name: parts[parts.length - 1] ?? "", depth: parts.length - 1, folders: [], files: [], total: 0, entered: 0 };
      nodes.set(path, found);
      if (path) node(parts.slice(0, -1).join(SEP)).folders.push(path);
    }
    return found;
  };
  node("");
  data.files.forEach(([id, folder, , state], at) => {
    const path = data.folders[folder] ?? "";
    node(path).files.push(at);
    const entered = (stateOf(id, state) & ENTERED) !== 0;
    for (const p of ["", ...ancestors(path)]) {
      const n = node(p);
      n.total += 1;
      if (entered) n.entered += 1;
    }
  });
  return nodes;
}

/**
 * The rows to draw, a folder's content only when it is in `expanded`. A closed folder that holds
 * the current file is marked `hasCurrent`.
 *
 * The order is the listing's own, which is the order previous / next file walks: a folder's files
 * first, then its folders as the listing reaches them. So stepping through the files moves the
 * mark straight down the tree. (Sorting names here, or putting folders first as an editor does,
 * would make the mark jump.) `pos` / `size`: the row's place among its siblings, from 1.
 */
export function visibleRows(
  data: TreeData, nodes: Map<string, FolderNode>, expanded: ReadonlySet<string>, currentId: number | null,
  stateOf: (id: number, state: number) => number = (_, s) => s,
): TreeRow[] {
  const rows: TreeRow[] = [];
  let currentPath: string | null = null;
  if (currentId !== null) {
    const hit = data.files.find((f) => f[0] === currentId);
    if (hit) currentPath = data.folders[hit[1]] ?? "";
  }
  const within = (path: string) => currentPath !== null && (currentPath === path || currentPath.startsWith(path + SEP));
  const walk = (path: string) => {
    const n = nodes.get(path);
    if (!n) return;
    const size = n.files.length + n.folders.length;
    let pos = 0;
    for (const at of n.files) {
      const [id, , name, state, records] = data.files[at];
      const bits = stateOf(id, state);
      rows.push({ kind: "file", key: "f:" + id, id, name, depth: n.depth + 1, pos: ++pos, size,
                  entered: (bits & ENTERED) !== 0, deleted: (bits & DELETED) !== 0, records: records ?? 1,
                  current: id === currentId });
    }
    for (const child of n.folders) {
      const c = nodes.get(child)!;
      const open = expanded.has(child);
      rows.push({ kind: "folder", key: "d:" + child, path: child, name: c.name, depth: c.depth, pos: ++pos, size,
                  total: c.total, entered: c.entered, open, hasCurrent: within(child) });
      if (open) walk(child);
    }
  };
  walk("");
  return rows;
}

/** The folder path of a file in the listing, or null when the listing does not hold it. */
export function folderOf(data: TreeData, id: number): string | null {
  const hit = data.files.find((f) => f[0] === id);
  return hit ? data.folders[hit[1]] ?? "" : null;
}

export type TreeKeyAction =
  | { type: "move"; key: string }
  | { type: "toggle"; path: string; open: boolean }
  | { type: "open"; id: number }
  | { type: "only"; path: string }
  | null;

/**
 * What a key does with the cursor on `rows[at]` (the WAI-ARIA tree pattern). Shift+Enter on a
 * folder narrows the list to it: no letter key is taken, those belong to the species palette.
 */
export function keyAction(rows: TreeRow[], at: number, key: string, shift = false): TreeKeyAction {
  if (!rows.length) return null;
  const row = rows[Math.max(0, Math.min(rows.length - 1, at))];
  const move = (to: number): TreeKeyAction => {
    const next = Math.max(0, Math.min(rows.length - 1, to));
    return next === at ? null : { type: "move", key: rows[next].key };
  };
  switch (key) {
    case "ArrowDown": return move(at + 1);
    case "ArrowUp": return move(at - 1);
    case "Home": return move(0);
    case "End": return move(rows.length - 1);
    case "ArrowRight":
      if (row.kind !== "folder") return null;
      return row.open ? move(at + 1) : { type: "toggle", path: row.path, open: true };
    case "ArrowLeft": {
      if (row.kind === "folder" && row.open) return { type: "toggle", path: row.path, open: false };
      for (let i = at - 1; i >= 0; i--) {
        const r = rows[i];
        if (r.kind === "folder" && r.depth === row.depth - 1) return { type: "move", key: r.key };
      }
      return null;
    }
    case "Enter": case " ":
      if (shift && key === "Enter") return row.kind === "folder" ? { type: "only", path: row.path } : null;
      return row.kind === "folder" ? { type: "toggle", path: row.path, open: !row.open } : { type: "open", id: row.id };
    default: return null;
  }
}

/** A DOM id for a row: ids may not hold white space, which a folder name may. */
export function rowDomId(key: string): string {
  return "tree-" + key.replace(/[%\s]/g, (c) => "%" + c.charCodeAt(0).toString(16));
}
