// Daily page -> Excel (user 24/11/2026): the two tables as on screen, plus one row per
// truck per day with the status in words and the hover text.
//
// Run: node tests/test_daily_xlsx.js
const fs = require('fs'), path = require('path'), vm = require('vm');
const html = fs.readFileSync(path.join(__dirname, '..', 'app', 'tool', 'index.html'), 'utf8');
const i = html.indexOf('function exportDailyXlsx(){');
const j = html.indexOf('function escAttr(s)', i);
const SRC = html.slice(i, j);
let FAIL = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) FAIL++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(60) + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}
check('the Excel button is on the Daily page', html.includes('id="dailyXlsxBtn"'), true);
check('the render keeps what is on screen for it', html.includes('window._DAILY_LAST={p, rows, fleetRows:fleetRows.slice(), subOf, SYM}'), true);

const D = ['2026-11-23', '2026-11-24'];
const p = {
  dates: D,
  sbd: { [D[0]]: { planned: 2, asPlanned: 1, offPlan: 1 }, [D[1]]: { planned: 1, waiting: 1 } },
  grid: {
    '20H01481': { totals: { circle: 1, half: 1 }, byDate: {
      [D[0]]: { sym: 'circle', tip: 'Plan 06:00\n  actual 06:20' },
      [D[1]]: { sym: 'half', note: '+5h', man: true, tip: 'Plan 08:00, actual 13:00' } } },
    '37H09305': { totals: { wait: 1 }, byDate: { [D[1]]: { sym: 'wait', wb: true } } },
  },
};
const rows = [{ label: 'Planned truck', f: 'planned' }, { label: 'Came as planned', f: 'asPlanned' },
              { label: 'Not as planned', f: 'offPlan' }, { label: 'Waiting', f: 'waiting' }];
const SYM = { circle: '●', half: '◐', wait: '⏳', cross: '✕', nogps: 'No GPS', square: '■', manual: '◆' };
const sheets = {}; let file = null;
const XLSX = {
  utils: { book_new: () => ({}), aoa_to_sheet: a => ({ aoa: a }), book_append_sheet: (wb, ws, n) => { sheets[n] = ws.aoa; } },
  writeFile: (wb, f) => { file = f; },
};
const ctx = {
  XLSX, alert: m => { throw new Error(m); },
  window: { _DAILY_LAST: { p, rows, fleetRows: ['37H09305', '20H01481'], subOf: pl => (pl[0] === '3' ? 'BBC' : 'Bac Nam'), SYM } },
  document: {
    querySelector: () => ({ textContent: 'In fleet' }),
    getElementById: () => ({ value: 'BBC' }),
    addEventListener() {},
  },
  Date,
  // 37H09305 joined the fleet on 24/11 (fleet "from" date): 23/11 is outside it.
  effOff: (pl, d) => (pl === '37H09305' && d < '2026-11-24' ? 'Not in the fleet yet (from 24/11) - not counted' : ''),
};
vm.createContext(ctx);
vm.runInContext(SRC + '\nexportDailyXlsx();', ctx);
check('four sheets', Object.keys(sheets), ['Daily status counts', 'Per-truck symbols', 'Per truck per day', 'About']);
check('counts: header', sheets['Daily status counts'][0], ['Status / Date', 'Total', D[0], D[1]]);
check('counts: a row with its total', sheets['Daily status counts'][1], ['Planned truck', 3, 2, 1]);
check('grid keeps the on-screen order', sheets['Per-truck symbols'].slice(1).map(r => r[0]), ['37H09305', '20H01481']);
check('grid cell: icon and marks only, no hours off (24/11)', sheets['Per-truck symbols'][2].slice(8), ['●', '◐ ◆']);
check('grid cell: weighbridge mark; a day before the truck joined is "–"', sheets['Per-truck symbols'][1].slice(8), ['–', '⏳ ⚠']);
check('per truck per day: status in words, no hours column, tip on one line',
  sheets['Per truck per day'][2], ['2026-11-23', '20H01481', 'Bac Nam', 'Came as planned', '', '', 'Plan 06:00 actual 06:20']);
check('the file name carries the period and company', file, 'Daily_performance_2026-11-23_to_2026-11-24_BBC.xlsx');
check('the About sheet says the fleet scope', sheets['About'][2], ['Fleet', 'In fleet']);

// With the server there (the live page): the page sends its data to be coloured there.
let sent = null, posted = null;
const ctx2 = Object.assign({}, ctx, {
  fetch: (u, o) => { posted = u; sent = JSON.parse(o.body); return { then: () => ({ then: () => ({ catch: () => {} }) }) }; },
  URL: { createObjectURL: () => 'blob:x', revokeObjectURL() {} }, setTimeout,
});
ctx2.window = Object.assign({}, ctx.window);
ctx2.document = Object.assign({}, ctx.document, { getElementById: id => (id === 'dailyCompanySel' ? { value: 'BBC' } : null) });
vm.createContext(ctx2);
vm.runInContext(SRC + '\nexportDailyXlsx();', ctx2);
check('live page: posts to the server', posted, '/api/tool/daily.xlsx');
check('...the counts with totals', sent.counts[0], { label: 'Planned truck', f: 'planned', total: 3, vals: [2, 1] });
check('...the grid in screen order, cells with the icon and marks, no hours', [sent.grid[1].plate, sent.grid[1].cells[1]],
  ['20H01481', { sym: 'half', man: true, wb: false, note: '' }]);
check('...one detail row per truck per day (the "–" day is not one)', sent.detail.length, 3);
check('...a day before the truck joined is sent as outside its dates', sent.grid[0].cells[0],
  { off: 'Not in the fleet yet (from 24/11) - not counted' });
check('...and the file name', sent.file, 'Daily_performance_2026-11-23_to_2026-11-24_BBC.xlsx');

// A deactivated truck is left out of the file (24/11/2026).
sent = null;
const ctx3 = Object.assign({}, ctx2, { isDeactivated: pl => pl === '37H09305' });
vm.createContext(ctx3);
vm.runInContext(SRC + '\nexportDailyXlsx();', ctx3);
check('a deactivated truck is not in the file', sent.grid.map(g => g.plate), ['20H01481']);
check('...nor in the per-day rows', [...new Set(sent.detail.map(x => x.plate))], ['20H01481']);
console.log(FAIL ? '\n' + FAIL + ' FAILED' : '\nall passed');
process.exit(FAIL ? 1 : 0);
