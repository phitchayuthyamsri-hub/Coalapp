// The Daily report judges the plan as a schedule (09/11/2026).
//
//   node tests/test_daily_schedule.js
//
// The plan is a slot agreed with the mine, so the report compares the time the
// GPS puts the truck at the mine with the plan time:
//   within 1 hour                    -> came as planned      (●)
//   1 to 12 hours early or late      -> not as planned       (◐)
//   not at the mine within 12 hours  -> did not come         (✕)
//   ...and no position at all in those 24 hours -> No GPS
// Before, the match was the calendar day: a truck queueing at 21:00 for a 07:00
// slot read "did not come" on the plan day and "came, not in plan" the day
// before. The report's own code is taken out of the page and run here.
const fs = require('fs'), path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'app', 'tool', 'index.html'), 'utf8');

let FAIL = 0;
function check(label, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  const ok = g === w;
  if (!ok) FAIL++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(60) + (ok ? '' : `got ${g} want ${w}`));
}

const a = html.indexOf("const LOCS=['MINE'");
const b = html.indexOf('function setPerfRange(');
if (a < 0 || b < 0) { console.log('  FAIL  could not find the report code'); process.exit(1); }
const region = html.slice(a, b);

process.env.TZ = 'Asia/Bangkok';
const harness = new Function('STATE', 'ACS', `
  var perfRange={from:null,to:null};
  function fleetScopeAllows(){ return true; }
  function normPlateStrict(p){ return String(p||'').toUpperCase().replace(/[^A-Z0-9]/g,''); }
  function _dinPad(n){ return String(n).padStart(2,'0'); }
  ${region}
  return { computePerf, setRange: (f,t)=>{ perfRange={from:f,to:t}; }, setCompany: c=>{ dailyCompany=c; } };
`);

// Wall-clock helpers: the page reads naive plan times as local (UTC+7 here).
const L = s => s;                                  // naive local ISO, as the plan carries
const T = s => new Date(s).toISOString();          // an actual: absolute, as the GPS gives

function run(plans, actuals, gpsHours, opt) {
  opt = opt || {};
  const ACS = { fleet: ['A1', 'B2', 'C3', 'D4', 'E5', 'F6'], fleetMeta: opt.meta || {}, plan: {}, actual: {},
                merges: {}, weigh: {}, manual: {}, wb: {}, issues: [], recos: [] };
  for (const p of plans)
    ACS.plan[p.plate + '|' + p.day] = { plate: p.plate, locs: { MINE: { in: L(p.at), out: null },
      BORDER: { in: null, out: null }, PORT: { in: null, out: null } }, ot: {} };
  for (const x of actuals)
    ACS.actual[x.plate + '|' + x.day] = { plate: x.plate, cyc: x.day,
      locs: { MINE: { in: T(x.at), out: null }, BORDER: { in: null, out: null }, PORT: { in: null, out: null } } };
  const STATE = { gpsHours: gpsHours || null, loadActual: [], nowMs: Date.parse(opt.now || '2026-12-01T00:00:00+07:00') };
  const h = harness(STATE, ACS);
  if (opt.company != null) h.setCompany(opt.company);
  return h.computePerf();
}

// every hour of 01-10/11 for everyone except the ones a case leaves dark
const allHours = (except) => {
  const plates = {};
  for (const pl of ['A1', 'B2', 'C3', 'D4', 'E5', 'F6']) {
    if ((except || []).includes(pl)) continue;
    plates[pl] = {};
    for (let d = 1; d <= 10; d++) plates[pl]['2026-11-' + String(d).padStart(2, '0')] = (1 << 24) - 1;
  }
  return { from: '2026-10-01', plates };
};

console.log('the schedule');
let p = run(
  [{ plate: 'A1', day: '2026-11-02', at: '2026-11-02T07:00' },     // 40 min late
   { plate: 'B2', day: '2026-11-02', at: '2026-11-02T07:00' },     // the evening before, 10 h early
   { plate: 'C3', day: '2026-11-02', at: '2026-11-02T08:00' },     // 13 h late
   { plate: 'D4', day: '2026-11-02', at: '2026-11-02T08:00' },     // nothing, GPS fine
   { plate: 'E5', day: '2026-11-02', at: '2026-11-02T08:00' }],    // nothing, GPS dark
  [{ plate: 'A1', day: '2026-11-02', at: '2026-11-02T07:40:00+07:00' },
   { plate: 'B2', day: '2026-11-01', at: '2026-11-01T21:00:00+07:00' },
   { plate: 'C3', day: '2026-11-02', at: '2026-11-02T21:00:00+07:00' },
   { plate: 'F6', day: '2026-11-02', at: '2026-11-02T10:00:00+07:00' }],    // no plan at all
  allHours(['E5']));
const day = p.sbd['2026-11-02'];
check('planned', day.planned, 5);
check('came as planned: only the 40-minutes-late one', day.asPlanned, 1);
check('not as planned: the one 10 h early, the day before', day.offPlan, 1);
check('did not come: 13 h late, and the one that never came', day.noShow, 2);
check('No GPS: the one whose GPS was dark', day.noGps, 1);
check('came, not in plan: F6, plus C3 13 h late on its own', day.unplan, 2);
check('...and B2 is not a stray arrival on 01/11', (p.sbd['2026-11-01'] || { unplan: 0 }).unplan, 0);
check('A1 cell is ● with no note', [p.grid.A1.byDate['2026-11-02'].sym, p.grid.A1.byDate['2026-11-02'].note], ['circle', '']);
check('B2 cell is ◐ -10h on the plan day', [p.grid.B2.byDate['2026-11-02'].sym, p.grid.B2.byDate['2026-11-02'].note], ['half', '-10h']);
check('C3 cell is ✕', p.grid.C3.byDate['2026-11-02'].sym, 'cross');
check('E5 cell is No GPS', p.grid.E5.byDate['2026-11-02'].sym, 'nogps');
check('the summary card counts', [p.asPlanned, p.offPlan, p.noGps, p.noShow], [1, 1, 1, 2]);
check('plan achievement is as planned only', p.pct, 20);

console.log('\nthe edges');
p = run([{ plate: 'A1', day: '2026-11-03', at: '2026-11-03T08:00' },
         { plate: 'B2', day: '2026-11-03', at: '2026-11-03T08:00' },
         { plate: 'C3', day: '2026-11-03', at: '2026-11-03T08:00' }],
        [{ plate: 'A1', day: '2026-11-03', at: '2026-11-03T09:00:00+07:00' },   // exactly 1 h
         { plate: 'B2', day: '2026-11-03', at: '2026-11-03T20:00:00+07:00' },   // exactly 12 h
         { plate: 'C3', day: '2026-11-03', at: '2026-11-03T07:01:00+07:00' }],  // 59 min early
        allHours());
check('exactly 1 h late is still as planned', p.grid.A1.byDate['2026-11-03'].sym, 'circle');
check('exactly 12 h late is not as planned', p.grid.B2.byDate['2026-11-03'].sym, 'half');
check('59 min early is as planned', p.grid.C3.byDate['2026-11-03'].sym, 'circle');

console.log('\none arrival, two plans');
p = run([{ plate: 'A1', day: '2026-11-04', at: '2026-11-04T07:00' },
         { plate: 'A1', day: '2026-11-05', at: '2026-11-05T07:00' }],
        [{ plate: 'A1', day: '2026-11-04', at: '2026-11-04T20:00:00+07:00' }],  // 13 h after one, 11 h before the next
        allHours());
check('it serves the plan it is closest to', [p.grid.A1.byDate['2026-11-04'].sym, p.grid.A1.byDate['2026-11-05'].sym], ['cross', 'half']);
check('...and counts once', p.sbd['2026-11-05'].offPlan + p.sbd['2026-11-04'].offPlan, 1);

console.log('\nwhat the GPS cannot tell');
p = run([{ plate: 'A1', day: '2026-11-06', at: '2026-11-06T08:00' }], [], null);
check('no hours from the server: did not come, as before', p.grid.A1.byDate['2026-11-06'].sym, 'cross');
const gh = allHours(['A1']);
gh.plates.A1 = { '2026-11-06': 1 << 19 };            // one position at 19:00, 11 h after the plan time
p = run([{ plate: 'A1', day: '2026-11-06', at: '2026-11-06T08:00' }], [], gh);
check('one position inside the 24 hours: did not come', p.grid.A1.byDate['2026-11-06'].sym, 'cross');
gh.plates.A1 = { '2026-11-06': 1 << 21 };            // 13 h after: outside
p = run([{ plate: 'A1', day: '2026-11-06', at: '2026-11-06T08:00' }], [], gh);
check('positions only outside it: No GPS', p.grid.A1.byDate['2026-11-06'].sym, 'nogps');

console.log('\nwaiting: the window is still open');
// it is 09/11 10:00; plans at 08:00 and 20:00 today, 23:00 yesterday, 08:00 yesterday
const W = [{ plate: 'A1', day: '2026-11-09', at: '2026-11-09T08:00' },
           { plate: 'B2', day: '2026-11-09', at: '2026-11-09T20:00' },
           { plate: 'C3', day: '2026-11-08', at: '2026-11-08T23:00' },
           { plate: 'D4', day: '2026-11-08', at: '2026-11-08T08:00' },
           { plate: 'E5', day: '2026-11-09', at: '2026-11-09T08:00' }];
const WA = [{ plate: 'E5', day: '2026-11-09', at: '2026-11-09T09:30:00+07:00' }];
p = run(W, WA, allHours(), { now: '2026-11-09T10:00:00+07:00' });
check('08:00 today, not there yet: waiting, not did not come', p.grid.A1.byDate['2026-11-09'].sym, 'wait');
check('20:00 tonight: waiting', p.grid.B2.byDate['2026-11-09'].sym, 'wait');
check('23:00 yesterday (window to 11:00 today): waiting', p.grid.C3.byDate['2026-11-08'].sym, 'wait');
check('08:00 yesterday (window closed 20:00): did not come', p.grid.D4.byDate['2026-11-08'].sym, 'cross');
check('one that already came is scored at once', p.grid.E5.byDate['2026-11-09'].sym, 'half');
check('the Waiting row counts', [p.sbd['2026-11-09'].waiting, p.sbd['2026-11-08'].waiting], [2, 1]);
check('waiting is not in did not come / No GPS', [p.noShow, p.noGps, p.waiting], [1, 0, 3]);
check('% of plan leaves the waiting out (0 of 2 judged)', p.pct, 0);
check('the tip says when it will be judged', p.grid.C3.byDate['2026-11-08'].tip, 'plan 23:00 · not at the mine yet · judged after 09/11 11:00');
p = run(W, WA, allHours(['B2']), { now: '2026-11-10T09:00:00+07:00' });
check('once the 12 hours pass: did not come ...', [p.grid.A1.byDate['2026-11-09'].sym, p.grid.C3.byDate['2026-11-08'].sym], ['cross', 'cross']);
check('... or No GPS', p.grid.B2.byDate['2026-11-09'].sym, 'nogps');
check('nothing waits any more', p.waiting, 0);
p = run([{ plate: 'A1', day: '2026-11-09', at: '' }], [], allHours(), { now: '2026-11-09T22:00:00+07:00' });
check('a plan with no time waits until its day is over', p.grid.A1.byDate['2026-11-09'].sym, 'wait');

console.log('\nthe subcontractor filter');
const meta = { A1: { company: 'BBC' }, B2: { company: 'BBC' }, C3: { company: 'PTS' }, D4: {}, E5: { company: 'PTS' }, F6: {} };
const S = [{ plate: 'A1', day: '2026-11-02', at: '2026-11-02T07:00' }, { plate: 'B2', day: '2026-11-02', at: '2026-11-02T07:00' },
           { plate: 'C3', day: '2026-11-02', at: '2026-11-02T07:00' }, { plate: 'D4', day: '2026-11-02', at: '2026-11-02T07:00' }];
const SA = [{ plate: 'A1', day: '2026-11-02', at: '2026-11-02T07:10:00+07:00' }, { plate: 'F6', day: '2026-11-02', at: '2026-11-02T10:00:00+07:00' }];
p = run(S, SA, allHours(), { meta, company: '' });
check('All: every company', [p.sbd['2026-11-02'].planned, Object.keys(p.grid).length], [4, 6]);
p = run(S, SA, allHours(), { meta, company: 'BBC' });
check('BBC: its 2 plans, 1 came as planned, 1 did not come', [p.sbd['2026-11-02'].planned, p.sbd['2026-11-02'].asPlanned, p.sbd['2026-11-02'].noShow], [2, 1, 1]);
check('BBC: only its trucks in the grid', Object.keys(p.grid).sort(), ['A1', 'B2']);
p = run(S, SA, allHours(), { meta, company: '-' });
check('(no company): D4 planned, F6 came not in plan', [p.sbd['2026-11-02'].planned, p.sbd['2026-11-02'].unplan, Object.keys(p.grid).sort()], [1, 1, ['D4', 'F6']]);

console.log('\nthe page');
check('Daily rows include Not as planned and No GPS',
      /label:'Not as planned'[\s\S]{0,200}label:'No GPS'/.test(html), true);
check('Daily rows include Waiting', /label:'Waiting'/.test(html), true);
check('the Daily page has the subcontractor dropdown', /id="dailyCompanySel"/.test(html), true);
check('the timing blob keeps the GPS hours',
      /gpsHours: STATE\.gpsHours/.test(html) && /STATE\.gpsHours = \(p\.gpsHours/.test(html), true);

console.log('\n' + (FAIL ? FAIL + ' FAILED' : 'ALL PASS'));
process.exit(FAIL ? 1 : 0);
