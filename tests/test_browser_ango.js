// The tool page rebuilds the GPS trips itself on load (recomputeSequences), so
// it must find A Ngo the same way app/engine.py does (10/11/2026: "why isn't
// there any A Ngo timing capture?" - the page threw the server's A Ngo away).
//
//   node tests/test_browser_ango.js
const fs = require('fs'), path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'app', 'tool', 'index.html'), 'utf8');
let FAIL = 0;
function check(label, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want), ok = g === w;
  if (!ok) FAIL++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(64) + (ok ? '' : `got ${g} want ${w}`));
}
const a = html.indexOf('function recomputeSequences() {'), b = html.indexOf('function sequenceMatchesFilters(');
if (a < 0 || b < 0) { console.log('  FAIL  could not find recomputeSequences'); process.exit(1); }
const fn = new Function('STATE', `
  function canonVisits(v){ return v; } function canonId(x){ return x; } function renderSequenceTable(){}
  ${html.slice(a, b)}
  recomputeSequences(); return STATE.sequences;`);

const T0 = Date.parse('2026-11-02T07:00:00+07:00');
const H = h => new Date(T0 + h * 3600e3);
const ROLES = { xppl: 'X', loading: 'L', border: 'B', ql49: 'Q', port: 'P', ango: 'A' };
const ANCH = Object.entries(ROLES).map(([r, id]) => ({ id, name: r === 'ango' ? 'A Ngo Warehouse' : r }));
function run(stops, roles) {
  const visits = stops.map(([id, i, o]) => ({ plate: 'A1', anchorId: id, anchorName: id, enter: H(i), exit: H(o) }));
  return fn({ roles: roles || ROLES, anchors: ANCH, visits, sequences: [] })[0] || {};
}

console.log('Mine : A Ngo');
let c = run([['X', 0, 2], ['L', 0.5, 1.5], ['B', 6, 9], ['A', 10, 12], ['B', 16, 17], ['X', 22, 23]]);
check('A Ngo on the way out', [c.angoIn, c.angoOut], [H(10), H(12)]);
check('the border crossing home after it', c.borderHomeOut, H(17));
check('no port: no port-based return leg', [c.chanMayIn, c.lalayBackIn], [null, null]);

console.log('\nMine : A Ngo : Chan May');
c = run([['X', 0, 2], ['B', 6, 9], ['A', 10, 11], ['Q', 13, 14], ['P', 20, 26], ['Q', 29, 30], ['B', 36, 37], ['X', 44, 45]]);
check('A Ngo between the border and QL49', c.angoIn, H(10));
check('QL49 and the port as before', [c.ql49OutIn, c.chanMayIn], [H(13), H(20)]);
check('return leg after the port as before; no border home', [c.lalayBackIn, c.borderHomeIn], [H(36), null]);

console.log('\nMine : Chan May, home by way of A Ngo');
c = run([['X', 0, 2], ['B', 6, 9], ['Q', 12, 13], ['P', 20, 26], ['A', 30, 31], ['B', 36, 37], ['X', 44, 45]]);
check('A Ngo after the port is not the stop out', [c.angoIn, c.borderHomeIn], [null, null]);

console.log('\nA Ngo role missing, found by its name');
const r2 = Object.assign({}, ROLES); delete r2.ango;
c = run([['X', 0, 2], ['B', 6, 9], ['A', 10, 12], ['X', 22, 23]], r2);
check('A Ngo Warehouse still found', c.angoIn, H(10));

console.log('\none mine stay: stepped out and back');
const runAll = (stops) => fn({ roles: ROLES, anchors: ANCH, visits: stops.map(([id, i, o]) => ({ plate: 'A1', anchorId: id, anchorName: id, enter: H(i), exit: H(o) })), sequences: [] });
let all = runAll([['X', 0, 1], ['X', 2, 3], ['L', 2.2, 2.8], ['B', 8, 10], ['X', 30, 31]]);
check('out and back with nowhere between: one trip, leaving at the last exit', [all.length, all[0].xpplOut, all[0].lalayOutIn], [2, H(3), H(8)]);
all = runAll([['X', 0, 1], ['X', 40, 41], ['B', 46, 47]]);
check('back after more than a day: two trips', all.length, 2);
all = runAll([['X', 0, 1], ['B', 6, 8], ['X', 20, 21]]);
check('a location in between: two trips, as before', [all.length, all[0].xpplOut], [2, H(1)]);

console.log('\nthe trip table');
check('A Ngo In / Out columns, sortable',
      html.includes('<th data-seqsort="angoIn">A Ngo — In</th><th data-seqsort="angoOut">A Ngo — Out</th>'), true);
check('...in the Excel export', html.includes("'A Ngo — In': c.angoIn ? fmtDateTime(c.angoIn)"), true);
check('a trip ending at A Ngo shows its crossing home in the back columns',
      html.includes('${f(c.lalayBackOut || c.borderHomeOut)}'), true);

console.log('\n' + (FAIL ? FAIL + ' FAILED' : 'ALL PASS'));
process.exit(FAIL ? 1 : 0);
