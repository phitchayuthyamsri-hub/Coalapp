// Reports > Scorecard works the four steps out of the Daily report's numbers,
// the GPS cycles and the BH-without-time declarations (10/11/2026).
//
//   node tests/test_scorecard.js
//
// The page's own code is taken out of index.html and run on a small corridor.
process.env.TZ = 'Asia/Bangkok';
const fs = require('fs'), path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'app', 'tool', 'index.html'), 'utf8');

let FAIL = 0;
function check(label, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want), ok = g === w;
  if (!ok) FAIL++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(64) + (ok ? '' : `got ${g} want ${w}`));
}
const a = html.indexOf("const LOCS=['MINE'"), b = html.indexOf('function setPerfRange(');
const s0 = html.indexOf('  // ======================= SCORECARD'), s1 = html.indexOf('  (function scWire(){');
if (a < 0 || b < 0 || s0 < 0 || s1 < 0) { console.log('  FAIL  could not find the code'); process.exit(1); }

const T = s => new Date(s + ':00+07:00');
const normPlate = s => String(s || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
const dk = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const I = x => x ? new Date(x).toISOString() : null;

function build(plans, seqs, untimed, company) {
  const ACS = { fleet: ['A1', 'B2', 'C3', 'D4'], plan: {}, actual: {}, merges: {}, weigh: {}, manual: {}, wb: {}, issues: [], recos: [],
                fleetMeta: { A1: { company: 'Bac Nam' }, B2: { company: 'PTS' }, C3: { company: 'Bac Nam' }, D4: { company: 'Bac Nam' } } };
  for (const p of plans)
    ACS.plan[p.plate + '|' + p.day] = { plate: p.plate, locs: { MINE: { in: p.mine, out: p.leave || null }, BORDER: { in: null, out: null }, PORT: { in: null, out: null } },
                                        ot: { mineReturn: p.back || null } };
  for (const c of seqs) ACS.actual[c.plate + '|' + dk(c.cycleDate)] = { plate: c.plate, cyc: dk(c.cycleDate), locs: {
    MINE: { in: I(c.xpplIn), out: I(c.xpplOut) }, LOADING: { in: I(c.loadingIn), out: I(c.loadingOut) },
    BORDER: { in: I(c.lalayOutIn), out: I(c.lalayOutOut) }, PORT: { in: I(c.chanMayIn), out: I(c.chanMayOut) },
    BORDER_BACK: { in: null, out: I(c.lalayBackOut) }, BACK_RET: I(c.xpplR), QL49_BACK: { in: null, out: I(c.ql49BackOut) } } };
  const all = { from: '2026-10-01', plates: {} };
  for (const pl of ACS.fleet) { all.plates[pl] = {}; for (let d = 1; d <= 9; d++) all.plates[pl]['2026-11-0' + d] = (1 << 24) - 1; }
  const STATE = { gpsHours: all, loadActual: [], sequences: seqs, filters: { fleetScope: 'in' }, nowMs: Date.parse('2026-11-20T00:00:00+07:00') };
  const f = new Function('STATE', 'ACS', `
    var perfRange={from:null,to:null};
    function fleetScopeAllows(p){ return true; }
    function isInFleet(p){ return true; }
    function isDeactivated(p){ return false; }
    function normPlateStrict(p){ return String(p||'').toUpperCase().replace(/[^A-Z0-9]/g,''); }
    function _dinPad(n){ return String(n).padStart(2,'0'); }
    function acpBuild(){}
    ${html.slice(a, b)}
    ${html.slice(s0, s1)}
    return { run: (f,t,c) => { scSel.company=c||''; return scMetrics(f,t,${JSON.stringify(untimed)},scSeqIndex()); }, scSummary, scDraw };`);
  return f(STATE, ACS);
}

const plans = [
  { plate: 'A1', day: '2026-11-02', mine: '2026-11-02T07:00', leave: '2026-11-02T08:00', back: '2026-11-03T19:30' },
  { plate: 'B2', day: '2026-11-02', mine: '2026-11-02T07:00' }];
const seqs = [
  { plate: 'A1', cycleDate: T('2026-11-02T07:30'), xpplIn: T('2026-11-02T07:30'), loadingIn: T('2026-11-02T07:40'), loadingOut: T('2026-11-02T08:30'),
    xpplOut: T('2026-11-02T08:40'), lalayOutOut: T('2026-11-02T16:00'), ql49OutOut: T('2026-11-02T20:00'), chanMayOut: T('2026-11-03T18:00'),
    xpplR: T('2026-11-03T20:00') },
  { plate: 'A1', cycleDate: T('2026-11-03T20:00'), xpplIn: T('2026-11-03T20:00'), loadingIn: T('2026-11-03T21:00'), loadingOut: T('2026-11-03T22:00') },
  { plate: 'D4', cycleDate: T('2026-11-02T20:00'), xpplIn: T('2026-11-02T20:00') }];
const untimed = { rows: [
  { day: '2026-11-02', plate: 'B2', key: 'B2', company: 'PTS', remark: '', group: '' },
  { day: '2026-11-02', plate: 'C3', key: 'C3', company: 'Bac Nam', remark: 'Bốc mỏ 01/11', group: 'prev' },
  { day: '2026-11-02', plate: 'D4', key: 'D4', company: 'Bac Nam', remark: '', group: '' }] };
const api = build(plans, seqs, untimed);

console.log('1-2: the Daily report numbers');
let m = api.run('2026-11-01', '2026-11-05');
check('planned / on time / did not come', [m.tot.planned, m.tot.asPlanned, m.tot.noShow], [2, 1, 1]);

console.log('\n3.1: each point on the road');
const cp = id => [m.cps[id].ok, m.cps[id].n];
check('arrive mine 30 min late: on time', cp('mine'), [1, 1]);
check('leave mine 30 min after plan: on time', cp('leave'), [1, 1]);
check('border crossed 16:00: inside 15:00-17:00', cp('border'), [1, 1]);
check('QL49 entered 20:00: inside 19:00-24:00', cp('ql49'), [1, 1]);
check('port left 18:00: outside 07:00-17:00', cp('port'), [0, 1]);
check('back 30 min after plan: on time', cp('back'), [1, 1]);
check('no time at a point = not counted there', cp('ql49b'), [0, 0]);

console.log('\n3.2-3.3: cycle and recovery');
check('cycle 36.5 h against 36.5 h planned', m.cyc.map(c => [c.plate, c.act, c.plan, c.diff]), [['A1', 36.5, 36.5, 0]]);
check('back 20:00, loading again 21:00: 1 h', m.rec.filter(r => r.plate === 'A1').map(r => [r.d, r.gap]), [['2026-11-03', 1]]);

console.log('\n4: opportunity lost');
check('no reason and no GPS visit: lost', m.lost['2026-11-02'], { prev: 1, repair: 0, came: 1, lost: 1 });
check('...the lost one is B2', m.lrows.filter(r => r.g === 'lost').map(r => r.plate), ['B2']);

console.log('\nthe subcontractor filter');
m = api.run('2026-11-01', '2026-11-05', 'Bac Nam');
check('Bac Nam: B2 (PTS) is out of the plan and the losses',
      [m.tot.planned, m.tot.noShow, m.lrows.map(r => r.plate)], [1, 0, ['C3', 'D4']]);

console.log('\nthe page');
const S = api.scSummary(api.run('2026-11-01', '2026-11-05'));
check('headline figures', [S.cameP, S.onP, S.lost, S.quickP], [50, 50, 1, 100]);
const out = api.scDraw(api.run('2026-11-01', '2026-11-05'), null);
check('draws the four steps', ['Did the plan happen?', 'Where the schedule slips', 'How long a cycle takes',
      'Back at the mine, loading again', 'Opportunity lost'].every(t => out.includes(t)), true);
check('the menu has it', /data-page="score">Scorecard</.test(html), true);
check('the page scrolls inside itself (10/11/2026: no scroll bar)',
      /\[data-page-panel="score"\] \.scwrap\{flex:1 1 auto;min-height:0;overflow-y:auto/.test(html), true);

console.log('\n' + (FAIL ? FAIL + ' FAILED' : 'ALL PASS'));
process.exit(FAIL ? 1 : 0);
