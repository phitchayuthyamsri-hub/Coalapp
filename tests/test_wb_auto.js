// Weighbridge loads the GPS never saw fill the Daily page (user 24/11/2026).
//
// Run: node tests/test_wb_auto.js
//
// 20C21788: 4 Nov night-shift load (at the mine 05/11 00:01-02:36 by GPS) and a
// 6 Nov day-shift load (43.21 t) with no GPS at all, even in TCT's history.
const fs = require('fs'), path = require('path'), vm = require('vm');
const html = fs.readFileSync(path.join(__dirname, '..', 'app', 'tool', 'index.html'), 'utf8');
const i = html.indexOf('function wbAutoKeys(');
const j = html.indexOf('function computePerf(', i);
let FAIL = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) FAIL++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(66) + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}
check('the page feeds weighbridge loads into the scoring',
  html.includes('wbAutoKeys((_seed&&_seed.weighLoads)||[]'), true);
const ctx = { normPlate: s => String(s || '').toUpperCase().replace(/[^A-Z0-9]/g, ''), cycKey: (p, d) => p + '|' + d, Date, Set };
vm.createContext(ctx);
vm.runInContext(html.slice(i, j), ctx);
const T = s => Date.parse(s);
const P = '20C21788';
const plan = (d, t) => ({ plate: P, d, key: P + '|' + d, t: T(d + 'T' + t + ':00') });
const planTime = p => p.t;
const W = 12 * 3600 * 1000;
const fleet = new Set([P, '20H00745']);
const acts = { [P]: [{ mi: T('2026-11-05T00:01:00') }] };          // GPS: at the mine 05/11 00:01
const missed = [plan('2026-11-05', '14:00'), plan('2026-11-06', '08:00')];
const run = (loads, a = acts, m = missed) => [...ctx.wbAutoKeys(loads, fleet, a, m, planTime, W)].sort();

check('6 Nov day-shift load, no GPS: fills the 6 Nov 08:00 plan', run([[P, '2026-11-06', 'd']]), [P + '|2026-11-06']);
check('4 Nov night-shift load: the GPS saw it (05/11 00:01), nothing filled', run([[P, '2026-11-04', 'n']]), []);
check('a load far from any missed plan: came-not-in-plan on its day',
  run([[P, '2026-11-09', 'd']]), [P + '|2026-11-09']);
check('two loads, one missed plan: one fills it, the other is its own day',
  run([[P, '2026-11-06', 'd'], [P, '2026-11-06', 'n']], acts, [plan('2026-11-06', '08:00')]),
  [P + '|2026-11-06']);
check('a truck not in the fleet is ignored', run([['99X99999', '2026-11-06', 'd']]), []);
check('the plate as the weighbridge writes it is matched', run([['20C-217.88', '2026-11-06', 'd']]), [P + '|2026-11-06']);
check('a night load fills the next morning\'s plan (06:00 is within 12 h)',
  run([[P, '2026-11-05', 'n']], {}, [plan('2026-11-06', '08:00')]), [P + '|2026-11-06']);
console.log(FAIL ? '\n' + FAIL + ' FAILED' : '\nall passed');
process.exit(FAIL ? 1 : 0);
