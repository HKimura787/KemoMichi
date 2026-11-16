const fs = require('node:fs');
const test = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');

require.extensions['.ts'] = (module, filename) => {
  const { outputText } = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }, fileName: filename,
  });
  module._compile(outputText, filename);
};
const { ancestors, buildTree, visibleRows, folderOf, keyAction, rowDomId, ENTERED, DELETED } = require('../src/tree.ts');

// Two cameras, a nested month folder, one file at the top level. Expected values are written
// out by hand here, not derived from the functions under test.
const data = {
  folders: ['CamA\\2026-04', 'CamB', ''],
  files: [
    [1, 0, 'a1.jpg', 0, 1], [2, 0, 'a2.jpg', ENTERED, 1], [3, 0, 'a3.jpg', ENTERED | DELETED, 1],
    [4, 1, 'b1.jpg', 0, 1], [5, 1, 'b2.jpg', DELETED, 3],
    [6, 2, 'root.jpg', ENTERED, 1],
  ],
};
const names = (rows) => rows.map((r) => (r.kind === 'folder' ? (r.open ? '-' : '+') : ' ') + r.name);

test('ancestors: every level of a path; the root has none', () => {
  assert.deepEqual(ancestors('A\\B\\C'), ['A', 'A\\B', 'A\\B\\C']);
  assert.deepEqual(ancestors('A'), ['A']);
  assert.deepEqual(ancestors(''), []);
});

test('buildTree: counts roll up to every folder above, and parents that hold no file exist', () => {
  const nodes = buildTree(data);
  const pick = (p) => { const n = nodes.get(p); return [n.total, n.entered, n.depth]; };
  assert.deepEqual(pick(''), [6, 3, -1]);
  assert.deepEqual(pick('CamA'), [3, 2, 0]);
  assert.deepEqual(pick('CamA\\2026-04'), [3, 2, 1]);
  assert.deepEqual(pick('CamB'), [2, 0, 0]);
  assert.deepEqual(nodes.get('').folders, ['CamA', 'CamB']);
  assert.deepEqual(nodes.get('').files, [5]);
  assert.equal(nodes.size, 4);
});

test('buildTree: folders keep the order the listing reaches them in (the order next / previous walks)', () => {
  const nodes = buildTree({ folders: ['Cam10', 'Cam2'], files: [[1, 0, 'x', 0, 1], [2, 1, 'y', 0, 1]] });
  assert.deepEqual(nodes.get('').folders, ['Cam10', 'Cam2']);
});

test('visibleRows: fully open, files come in the listing order (files of a folder before its folders)', () => {
  // as the server sorts: a folder's own files, then what is below it, three levels deep
  const sorted = {
    folders: ['', 'A', 'A\\B', 'A\\B\\C', 'D'],
    files: [[11, 0, 'r', 0, 1], [12, 1, 'a', 0, 1], [13, 2, 'b', 0, 1], [14, 3, 'c', 0, 1], [15, 4, 'd', 0, 1]],
  };
  const rows = visibleRows(sorted, buildTree(sorted), new Set(['A', 'A\\B', 'A\\B\\C', 'D']), null);
  assert.deepEqual(names(rows), [' r', '-A', ' a', '-B', ' b', '-C', ' c', '-D', ' d']);
  assert.deepEqual(rows.filter((r) => r.kind === 'file').map((r) => r.id), [11, 12, 13, 14, 15]);
  assert.deepEqual(rows.map((r) => r.depth), [0, 0, 1, 1, 2, 2, 3, 0, 1]);
  // place among siblings: the root holds r, A, D; A holds a, B; C holds c alone
  assert.deepEqual(rows.map((r) => r.pos + '/' + r.size), ['1/3', '2/3', '1/2', '2/2', '1/2', '2/2', '1/1', '3/3', '1/1']);
});

test('buildTree: names that differ only in case are different folders', () => {
  const mixed = { folders: ['cama', 'CamA'], files: [[1, 0, 'x', ENTERED, 1], [2, 1, 'y', 0, 1]] };
  const nodes = buildTree(mixed);
  assert.deepEqual(nodes.get('').folders, ['cama', 'CamA']);
  assert.deepEqual([nodes.get('cama').entered, nodes.get('CamA').entered], [1, 0]);
});

test('rowDomId: no white space in the id, and different keys stay different', () => {
  assert.equal(rowDomId('d:CamA\\2026-04'), 'tree-d:CamA\\2026-04');
  assert.equal(rowDomId('d:Cam A'), 'tree-d:Cam%20A');
  assert.equal(rowDomId('d:Cam\tA'), 'tree-d:Cam%9A');
  assert.notEqual(rowDomId('d:Cam A'), rowDomId('d:Cam%20A'));
  assert.equal(rowDomId('f:12'), 'tree-f:12');
});

test('buildTree and visibleRows: empty listing gives a root and no rows', () => {
  const empty = { folders: [], files: [] };
  const nodes = buildTree(empty);
  assert.deepEqual([nodes.size, nodes.get('').total], [1, 0]);
  assert.deepEqual(visibleRows(empty, nodes, new Set(), null), []);
  assert.equal(keyAction([], 0, 'ArrowDown'), null);
});

test('visibleRows: all closed shows top-level files then top folders; nothing inside', () => {
  const rows = visibleRows(data, buildTree(data), new Set(), null);
  assert.deepEqual(names(rows), [' root.jpg', '+CamA', '+CamB']);
  assert.ok(rows.every((r) => r.kind === 'file' || !r.hasCurrent));
});

test('visibleRows: an open folder shows its content, with depth', () => {
  const rows = visibleRows(data, buildTree(data), new Set(['CamA', 'CamA\\2026-04']), 2);
  assert.deepEqual(names(rows), [' root.jpg', '-CamA', '-2026-04', ' a1.jpg', ' a2.jpg', ' a3.jpg', '+CamB']);
  assert.deepEqual(rows.map((r) => r.depth), [0, 0, 1, 2, 2, 2, 0]);
  assert.deepEqual(rows.filter((r) => r.kind === 'file' && r.current).map((r) => r.id), [2]);
  const a3 = rows.find((r) => r.kind === 'file' && r.id === 3);
  assert.deepEqual([a3.entered, a3.deleted], [true, true]);
});

test('visibleRows: an open parent with a closed child does not show the grandchildren', () => {
  const rows = visibleRows(data, buildTree(data), new Set(['CamA']), null);
  assert.deepEqual(names(rows), [' root.jpg', '-CamA', '+2026-04', '+CamB']);
});

test('visibleRows: closed folders above the current file are marked; others are not', () => {
  const rows = visibleRows(data, buildTree(data), new Set(), 2);
  const mark = Object.fromEntries(rows.filter((r) => r.kind === 'folder').map((r) => [r.name, r.hasCurrent]));
  assert.deepEqual(mark, { CamA: true, CamB: false });
  // "CamB" must not count as holding a file of a folder that merely starts with its name
  const similar = { folders: ['Cam', 'CamB'], files: [[1, 0, 'x', 0, 1], [2, 1, 'y', 0, 1]] };
  const rows2 = visibleRows(similar, buildTree(similar), new Set(), 2);
  assert.deepEqual(rows2.map((r) => [r.name, r.hasCurrent]), [['Cam', false], ['CamB', true]]);
});

test('visibleRows: a current file the listing does not hold marks nothing', () => {
  const rows = visibleRows(data, buildTree(data), new Set(), 999);
  assert.ok(rows.every((r) => (r.kind === 'folder' ? !r.hasCurrent : !r.current)));
  assert.equal(folderOf(data, 999), null);
  assert.equal(folderOf(data, 6), '');
  assert.equal(folderOf(data, 1), 'CamA\\2026-04');
});

test('fresher state replaces what the listing says; record counts come from the listing', () => {
  const stateOf = (id, state) => (id === 4 ? ENTERED : id === 2 ? 0 : state);
  const nodes = buildTree(data, stateOf);
  assert.deepEqual([nodes.get('CamA').entered, nodes.get('CamB').entered], [1, 1]);
  const rows = visibleRows(data, nodes, new Set(['CamB']), null, stateOf);
  const b = rows.filter((r) => r.kind === 'file' && r.depth === 1);
  assert.deepEqual(b.map((r) => [r.id, r.entered, r.records]), [[4, true, 1], [5, false, 3]]);
});

test('keyAction: arrows move and stop at the ends', () => {
  const rows = visibleRows(data, buildTree(data), new Set(), null); // root.jpg +CamA +CamB
  assert.deepEqual(keyAction(rows, 1, 'ArrowDown'), { type: 'move', key: 'd:CamB' });
  assert.deepEqual(keyAction(rows, 1, 'ArrowUp'), { type: 'move', key: 'f:6' });
  assert.equal(keyAction(rows, 0, 'ArrowUp'), null);
  assert.equal(keyAction(rows, 2, 'ArrowDown'), null);
  assert.deepEqual(keyAction(rows, 0, 'End'), { type: 'move', key: 'd:CamB' });
  assert.deepEqual(keyAction(rows, 2, 'Home'), { type: 'move', key: 'f:6' });
  assert.equal(keyAction(rows, 0, 'x'), null);
});

test('keyAction: right opens then enters; left closes, then goes to the parent', () => {
  const closed = visibleRows(data, buildTree(data), new Set(), null);
  assert.deepEqual(keyAction(closed, 1, 'ArrowRight'), { type: 'toggle', path: 'CamA', open: true });
  assert.equal(keyAction(closed, 1, 'ArrowLeft'), null); // closed, top level: nowhere to go
  assert.equal(keyAction(closed, 0, 'ArrowRight'), null); // a file
  // root.jpg -CamA -2026-04 a1 a2 a3 +CamB
  const open = visibleRows(data, buildTree(data), new Set(['CamA', 'CamA\\2026-04']), null);
  assert.deepEqual(keyAction(open, 1, 'ArrowRight'), { type: 'move', key: 'd:CamA\\2026-04' });
  assert.deepEqual(keyAction(open, 2, 'ArrowLeft'), { type: 'toggle', path: 'CamA\\2026-04', open: false });
  assert.deepEqual(keyAction(open, 4, 'ArrowLeft'), { type: 'move', key: 'd:CamA\\2026-04' }); // a2.jpg → its folder
  assert.equal(keyAction(open, 0, 'ArrowLeft'), null); // top-level file has no parent row
});

test('keyAction: Enter and Space toggle a folder and open a file', () => {
  const rows = visibleRows(data, buildTree(data), new Set(), null);
  assert.deepEqual(keyAction(rows, 2, 'Enter'), { type: 'toggle', path: 'CamB', open: true });
  assert.deepEqual(keyAction(rows, 0, ' '), { type: 'open', id: 6 });
});

test('keyAction: Shift+Enter narrows the list to a folder; on a file, and with Space, it does not', () => {
  const rows = visibleRows(data, buildTree(data), new Set(), null); // root.jpg +CamA +CamB
  assert.deepEqual(keyAction(rows, 2, 'Enter', true), { type: 'only', path: 'CamB' });
  assert.equal(keyAction(rows, 0, 'Enter', true), null);
  assert.deepEqual(keyAction(rows, 2, ' ', true), { type: 'toggle', path: 'CamB', open: true });
  assert.equal(keyAction(rows, 2, 'f'), null); // letters stay free for the species keys
});
