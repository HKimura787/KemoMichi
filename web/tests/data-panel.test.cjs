const fs = require('node:fs');
const test = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

// Compile the actual components with the existing TypeScript dependency.
for (const extension of ['.ts', '.tsx']) {
  require.extensions[extension] = (module, filename) => {
    const { outputText } = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020 },
      fileName: filename,
    });
    module._compile(outputText, filename);
  };
}
const { DataPanel } = require('../src/components/DataPanel.tsx');

const field = (type, dataLabel, visible = true) => ({
  id: dataLabel, type, dataLabel, label: `Template ${dataLabel}`, visible, standard: false,
  choices: ['A', 'B'], includeEmptyChoice: true,
});
function render({ controls, items, values = {}, bulkCount = 0, locked = new Set() }) {
  return renderToStaticMarkup(React.createElement(DataPanel, {
    controls, palette: { items, single: false }, row: { id: 1, values }, bulkCount, locked,
    readOnly: false, onChange: async () => {}, onCopyPrevious: () => {}, canCopyPrevious: false,
  }));
}

test('unselected and selected species retain their counter input with its template label', () => {
  const controls = [field('Flag', 'Deer'), field('Counter', 'DeerCount')];
  const items = [{ flag: 'Deer', counter: 'DeerCount', key: '1' }];
  for (const selected of ['false', 'true']) {
    const html = render({ controls, items, values: { Deer: selected, DeerCount: '0' } });
    assert.match(html, /<label[^>]*>Template DeerCount<\/label>/);
    assert.equal((html.match(/id="f-DeerCount"/g) || []).length, 1);
    assert.match(html, /aria-label="Template DeerCount \+1"/);
  }
  const bulk = render({ controls, items, bulkCount: 2 });
  assert.match(bulk, /id="f-DeerCount"/);
  assert.doesNotMatch(bulk, /aria-label="Template DeerCount \+1"/);
});

test('stale palette references cannot hide notes or locked fields, and hidden fields stay hidden', () => {
  const controls = [field('Flag', 'Deer'), field('Note', 'Notes'), field('Counter', 'Hidden', false),
    field('Flag', 'HiddenFlag', false), field('Flag', 'EventFlag')];
  const html = render({ controls, items: [
    { flag: 'Deer', counter: 'Notes' }, { flag: 'HiddenFlag', counter: 'Hidden' },
    { flag: 'EventFlag', counter: null }, { flag: 'Missing', counter: 'Notes' },
  ], locked: new Set(['EventFlag']) });
  assert.match(html, /id="f-Notes"/);
  assert.match(html, /id="f-EventFlag" disabled=""/);
  assert.doesNotMatch(html, /Template Hidden/);
});

test('every visible user field type appears in the input panel', () => {
  const types = ['Counter', 'FixedChoice', 'MultiChoice', 'Flag', 'Note', 'MultiLine', 'AlphaNumeric',
    'IntegerAny', 'IntegerPositive', 'DecimalAny', 'DecimalPositive', 'DateTime_', 'Date_', 'Time_'];
  const html = render({ controls: types.map((type, i) => field(type, `Column${i}`)), items: [] });
  types.forEach((_, i) => assert.match(html, new RegExp(`Template Column${i}<`)));
});
