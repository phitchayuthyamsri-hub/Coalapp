// The Timeline legend: one entry per place, in the colour its bars are drawn.
//
// 07/10/2026 "legend and actual bar color doesn't match". The anchor store
// held every zone twice - the server's copy (ids 1-7) and an older browser
// copy (anc_default_0..5) that the roles and the visits still point at - so
// the legend listed thirteen entries for seven places, the six unused server
// copies in the "unmapped" red. A Ngo had no role colour and drew in that same
// red, and Detour's near-black swatch vanished on the dark page.
const fs = require('fs'), vm = require('vm');
// Line endings normalised: a Windows checkout has CRLF.
const html = fs.readFileSync('app/tool/index.html', 'utf8').replace(/\r\n/g, '\n');
const grab = (re, what) => { const m = html.match(re); if (!m) throw new Error('not found: ' + what); return m[0]; };
const src = [
  grab(/const ROLE_COLORS = \{[\s\S]*?\n\};/, 'ROLE_COLORS'),
  grab(/const UNMAPPED_COLOR = [^\n]*/, 'UNMAPPED_COLOR'),
  grab(/const DETOUR_COLOR {3}= [^\n]*/, 'DETOUR_COLOR'),
  grab(/function effectiveColor\(anchorId, anchorName\) \{[\s\S]*?\n\}/, 'effectiveColor'),
  grab(/function renderTimelineLegend\(\) \{[\s\S]*?\n\}\n/, 'renderTimelineLegend'),
].join('\n');

const legendEl = {innerHTML: '', querySelectorAll(){ return []; }};
const sandbox = {
  STATE: {
    anchors: [
      ...['QL49', 'Chan May port', 'XPPL Mine', 'XPPL Loading area', 'Lalay border', 'Detour route', 'A Ngo Warehouse']
        .map((name, i) => ({id: String(i + 1), name})),
      ...['QL49', 'Chan May port', 'XPPL Mine', 'XPPL Loading area', 'Lalay border', 'Detour route']
        .map((name, i) => ({id: 'anc_default_' + i, name})),
    ],
    roles: {ql49: 'anc_default_0', port: 'anc_default_1', xppl: 'anc_default_2',
            loading: 'anc_default_3', border: 'anc_default_4', detour: 'anc_default_5', ango: '7'},
    timelineHidden: new Set(),
  },
  document: {getElementById: id => id === 'timelineLegend' ? legendEl : null},
  escapeHtml: s => String(s), renderTimeline(){},
};
vm.createContext(sandbox);
vm.runInContext(src, sandbox);

let fail = 0;
function is(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want); if (!ok) fail++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(58)
    + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}
const color = (id, name) => vm.runInContext('effectiveColor(' + JSON.stringify(id) + ',' + JSON.stringify(name) + ')', sandbox);

console.log('bar colours');
is('a bar on the old copy keeps its role colour', color('anc_default_0', 'QL49'), '#f57c00');
is('the server copy of the same place: the same colour', color('1', 'QL49'), '#f57c00');
is('A Ngo has a colour of its own', color('7', 'A Ngo Warehouse'), '#8d6e63');
is('...which is not the unmapped red', color('7', 'A Ngo Warehouse') !== '#ff3b30', true);
is('a zone nobody mapped is still red', color('99', 'New zone'), '#ff3b30');

console.log('\nthe legend');
vm.runInContext('renderTimelineLegend()', sandbox);
const out = legendEl.innerHTML;
const names = [...out.matchAll(/<\/span>\s*([^<]+?)\s*<\/label>/g)].map(m => m[1]);
is('one entry per place, not per id', names,
   ['QL49', 'Chan May port', 'XPPL Mine', 'XPPL Loading area', 'Lalay border', 'Detour route', 'A Ngo Warehouse']);
is('no red swatch left in the legend', /background:#ff3b30/.test(out), false);
is("an entry's checkbox carries every id of that place", /data-tl-anchor="1\|anc_default_0"/.test(out), true);
is('dark swatches get an outline on the dark page', /box-shadow:0 0 0 1px/.test(out), true);

console.log(fail ? '\n  ' + fail + ' FAILING' : '\n  all pass');
process.exit(fail ? 1 : 0);
