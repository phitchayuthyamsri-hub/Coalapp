// Per-truck daily symbols: sorting a date sorts by that day's status (user 20/11/2026).
//
// Run: node tests/test_daily_date_sort.js
//
// Order: came as planned, not as planned, waiting, did not come, No GPS, came not
// in plan, manual/weighbridge only; trucks with nothing that day at the bottom.
// Not as planned is by hours off the plan, ascending, in both directions.
const fs = require('fs'), path = require('path'), vm = require('vm');
const html = fs.readFileSync(path.join(__dirname, '..', 'app', 'tool', 'index.html'), 'utf8');
const i = html.indexOf("if(dailySort.col==='__plate'){ fleetRows.sort(");
const j = html.indexOf("let sb='<tbody>';", i);
const SORT = html.slice(i, j);
const SUB = { C_half_late8: 'PTS', D_circle: 'Bac Nam', E_cross: 'BBC', K_circle: 'Bac Nam' };
let FAIL = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) FAIL++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(56) + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}
const D = '2026-11-19';
const cells = {
  A_blank: null, B_square: { sym: 'square' }, C_half_late8: { sym: 'half', dm: 480 }, D_circle: { sym: 'circle' },
  E_cross: { sym: 'cross' }, F_half_early2: { sym: 'half', dm: -120 }, G_nogps: { sym: 'nogps' }, H_wait: { sym: 'wait' },
  I_half_late3: { sym: 'half', dm: 180 }, J_manual: { sym: null, man: true }, K_circle: { sym: 'circle' }, L_blank: null,
};
const p = { grid: {} };
for (const [k, v] of Object.entries(cells)) p.grid[k] = { byDate: v ? { [D]: v } : {} };
function run(col, dir) {
  const ctx = { p, dailySort: { col, dir }, fleetRows: Object.keys(cells).sort().reverse(), subOf: pl => SUB[pl] || '' };
  vm.createContext(ctx); vm.runInContext(SORT, ctx); return ctx.fleetRows;
}
check('date ascending: status order, not-as-planned by hours', run(D, 1),
  ['D_circle', 'K_circle', 'F_half_early2', 'I_half_late3', 'C_half_late8', 'H_wait', 'E_cross', 'G_nogps', 'B_square', 'J_manual', 'A_blank', 'L_blank']);
check('date descending: status order reversed, blanks last', run(D, -1),
  ['J_manual', 'B_square', 'G_nogps', 'E_cross', 'H_wait', 'F_half_early2', 'I_half_late3', 'C_half_late8', 'D_circle', 'K_circle', 'A_blank', 'L_blank']);
check('Subcontractor sort: by company, none last', run('__sub', 1).slice(0, 5), ['D_circle', 'K_circle', 'E_cross', 'C_half_late8', 'A_blank']);
check('plate sort unchanged', run('__plate', 1).slice(0, 3), ['A_blank', 'B_square', 'C_half_late8']);

// The six totals sort too (24/11/2026): first click most first, again least first, plate breaks ties.
p.grid.E_cross.totals = { cross: 22 };
p.grid.C_half_late8.totals = { cross: 4, half: 9 };
p.grid.H_wait.totals = { cross: 4 };
p.grid.D_circle.totals = { circle: 3 };
check('✕ total: most first', run('__sum_cross', 1).slice(0, 3), ['E_cross', 'C_half_late8', 'H_wait']);
check('✕ total: again, least first (ties stay A-Z)', run('__sum_cross', -1).slice(-3), ['C_half_late8', 'H_wait', 'E_cross']);
check('◐ total: most first', run('__sum_half', 1)[0], 'C_half_late8');
check('the total headers are sortable', html.includes('data-col="__sum_${k}"'), true);
console.log(FAIL ? '\n' + FAIL + ' FAILED' : '\nall passed');
process.exit(FAIL ? 1 : 0);
