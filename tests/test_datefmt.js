// Dates read DD/MM/YYYY everywhere, and are still stored YYYY-MM-DD.
//
// Two halves are pinned here: the shared formatter that rewrites what a person
// reads, and the grid, which must turn a date typed or pasted day-first back
// into the stored form - or "16/09/2026" would be saved as it was typed and the
// planner could not read it.
const fs = require('fs'), vm = require('vm');

let fail = 0;
function is(label, got, want){
  const ok = got === want;
  if (!ok) fail++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(58)
    + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}

const sandbox = {console, Date, setTimeout, window: {}};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('app/static/datefmt.js', 'utf8'), sandbox);
const F = sandbox.DateFmt;

console.log('formatter');
is('a stored date reads day first', F.dmy('2026-09-16'), '16/09/2026');
is('...with a time on it, the date alone', F.dmy('2026-09-16T05:00'), '16/09/2026');
is('a blank stays blank', F.dmy(''), '');
is('a Date reads day first with the time', F.dt(new Date(2026, 8, 16, 5, 7)), '16/09/2026 05:07');
is('a date inside a sentence', F.text('Sheet for 2026-09-16 is ready'), 'Sheet for 16/09/2026 is ready');
is('a date and time with T', F.text('issued 2026-09-15T16:30'), 'issued 15/09/2026 16:30');
is('a date and time with seconds', F.text('2026-09-15 16:30:12'), '15/09/2026 16:30');
is('two dates in one line', F.text('2026-09-14 → 2026-09-20'), '14/09/2026 → 20/09/2026');
is('a file name with a packed date is left alone', F.text('plan_20260916.xlsx'), 'plan_20260916.xlsx');
is('a dashed date inside a file name converts too', F.text('dispatch_plan_2026-09-14_BN.xlsx'),
   'dispatch_plan_14/09/2026_BN.xlsx');
is('not a real month: left alone', F.text('2026-13-01'), '2026-13-01');
is('glued to more digits: left alone', F.text('12026-09-16'), '12026-09-16');
is('a range of numbers is not a date', F.text('1200-1500 trucks'), '1200-1500 trucks');

console.log('\ngrid: dates typed or pasted day first are stored YYYY-MM-DD');
const g = {console, Date, window: {}};
g.window = g;
vm.createContext(g);
vm.runInContext(fs.readFileSync('app/static/grid.js', 'utf8'), g);
const N = g.Grid && g.Grid.normDate;
is('the grid exposes its date reader', typeof N, 'function');
if (typeof N === 'function') {
  is('16/09/2026', N('16/09/2026'), '2026-09-16');
  is('16-09-2026', N('16-09-2026'), '2026-09-16');
  is('16-09-26 (the sheet form)', N('16-09-26'), '2026-09-16');
  is('5/9/2026', N('5/9/2026'), '2026-09-05');
  is('16.09.2026', N('16.09.2026'), '2026-09-16');
  is('already stored form', N('2026-09-16'), '2026-09-16');
  is('31/02/2026 is not a day', N('31/02/2026'), null);
  is('words are not a date', N('tomorrow'), null);
  is('blank stays blank', N(''), '');
}

console.log(fail ? '\n  ' + fail + ' FAILING' : '\n  all pass');
process.exit(fail ? 1 : 0);
