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
    ACS.plan[p.plate + '|' + p.day] = { plate: p.plate, locs: { MINE: { in: p.mine, out: p.leave || null }, BORDER: { in: null, out: null }, PORT: { in: null, out: p.port || null } },
                                        ot: { mineReturn: p.back || null }, route: p.route || '', ango: p.ango || null };
  for (const c of seqs) ACS.actual[c.plate + '|' + dk(c.cycleDate)] = { plate: c.plate, cyc: dk(c.cycleDate), locs: {
    MINE: { in: I(c.xpplIn), out: I(c.xpplOut) }, LOADING: { in: I(c.loadingIn), out: I(c.loadingOut) },
    BORDER: { in: I(c.lalayOutIn), out: I(c.lalayOutOut) }, PORT: { in: I(c.chanMayIn), out: I(c.chanMayOut) },
    BORDER_BACK: { in: null, out: I(c.lalayBackOut) }, BACK_RET: I(c.xpplR), QL49_BACK: { in: null, out: I(c.ql49BackOut) },
    ANGO: c.angoIn ? { in: I(c.angoIn), out: I(c.angoOut) } : undefined,
    DETOUR: c.detourIn ? { in: I(c.detourIn), out: I(c.detourOut) } : undefined,
    BORDER_HOME: c.borderHomeOut ? { in: null, out: I(c.borderHomeOut) } : undefined } };
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
    return { run: (f,t,c) => { scSel.company=c||''; return scMetrics(f,t,${JSON.stringify(untimed)},scSeqIndex()); }, scSummary, scDraw,
             setRoute: r => { scSel.route = r; } };`);
  return f(STATE, ACS);
}

const plans = [
  { plate: 'A1', day: '2026-11-02', mine: '2026-11-02T07:00', leave: '2026-11-02T08:00', port: '2026-11-03T17:00', back: '2026-11-03T19:30' },   // no route on the plan = Mine : Chan May
  { plate: 'B2', day: '2026-11-02', mine: '2026-11-02T07:00' }];
const seqs = [
  { plate: 'A1', cycleDate: T('2026-11-02T07:30'), xpplIn: T('2026-11-02T07:30'), loadingIn: T('2026-11-02T07:40'), loadingOut: T('2026-11-02T08:30'),
    xpplOut: T('2026-11-02T08:40'), lalayOutOut: T('2026-11-02T16:00'), ql49OutOut: T('2026-11-02T20:00'), chanMayOut: T('2026-11-03T18:00'),
    detourIn: T('2026-11-03T18:40'), detourOut: T('2026-11-03T18:50'), xpplR: T('2026-11-03T20:00') },
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
check('no time at a point = not counted there', cp('borderb'), [0, 0]);
check('QL49 empty is no longer judged on its window', m.cps.ql49b, undefined);
const seqsNoLoad = seqs.map(c => { const o = Object.assign({}, c); delete o.loadingIn; delete o.loadingOut; return o; });
const mNL = build(plans, seqsNoLoad, untimed).run('2026-11-01', '2026-11-05');
check('leave mine = the mine departure: measured even with no loading-area visit', [mNL.cps.leave.ok, mNL.cps.leave.n], [1, 1]);
check('the way home is counted: A1 went home by Dakrong', m.way, { n: 1, ql49: 0, dak: 1, none: 0 });
const seqsBoth = seqs.map(c => c.detourIn ? Object.assign({}, c, { ql49BackIn: T('2026-11-03T18:20'), ql49BackOut: T('2026-11-03T18:30') }) : c);
check('passed QL49 and Dakrong: Dakrong only, never both', build(plans, seqsBoth, untimed).run('2026-11-01', '2026-11-05').way, { n: 1, ql49: 0, dak: 1, none: 0 });
const outW = api.scDraw(m, null);
check('QL49 and Dakrong stacked in one column, QL49 on top', /class="scnode scway">[\s\S]*>QL49<\/div>[\s\S]*>Dakrong \(QL9\)<\/div>/.test(outW), true);
check('...counted, not judged (0 of 1 / 1 of 1)', outW.includes('>0 of 1</div>') && outW.includes('>1 of 1</div>'), true);

console.log('\n3.2-3.3: cycle and recovery');
check('cycle 36.5 h against 36.5 h planned', m.cyc.map(c => [c.plate, c.act, c.plan, c.diff]), [['A1', 36.5, 36.5, 0]]);
check('front haul: 34.5 h against 34 h (mine to leaving the port)', m.cyc[0].fh, { act: 34.5, plan: 34 });
check('back haul: 2 h against 2.5 h (port to the mine)', m.cyc[0].bh, { act: 2, plan: 2.5 });
check('unloaded 18:00, back at the mine 20:00: 2 h, on the unload day', m.rec.filter(r => r.plate === 'A1').map(r => [r.d, r.gap]), [['2026-11-03', 2]]);

console.log('\n4: opportunity lost');
check('no reason and no GPS visit: lost', m.lost['2026-11-02'], { prev: 1, repair: 0, came: 1, lost: 1 });
check('...the lost one is B2', m.lrows.filter(r => r.g === 'lost').map(r => r.plate), ['B2']);

console.log('\nthe subcontractor filter');
m = api.run('2026-11-01', '2026-11-05', 'Bac Nam');
check('Bac Nam: B2 (PTS) is out of the plan and the losses',
      [m.tot.planned, m.tot.noShow, m.lrows.map(r => r.plate)], [1, 0, ['C3', 'D4']]);

console.log('\neach route judged at its own points');
const plA = [{ plate: 'A1', day: '2026-11-02', mine: '2026-11-02T07:00', leave: '2026-11-02T08:00', ango: '2026-11-02T17:00',
               back: '2026-11-03T08:00', route: 'Mine : A Ngo' },
             { plate: 'C3', day: '2026-11-02', mine: '2026-11-02T07:00', route: 'Mine : A Ngo' }];
const sqA = [{ plate: 'A1', cycleDate: T('2026-11-02T07:20'), xpplIn: T('2026-11-02T07:20'), loadingOut: T('2026-11-02T08:10'),
               lalayOutOut: T('2026-11-02T16:00'), angoIn: T('2026-11-02T17:30'), angoOut: T('2026-11-02T19:00'),
               borderHomeOut: T('2026-11-03T02:00'), xpplR: T('2026-11-03T08:30') },
             { plate: 'C3', cycleDate: T('2026-11-02T07:10'), xpplIn: T('2026-11-02T07:10'), lalayOutOut: T('2026-11-02T16:30'),
               ql49OutOut: T('2026-11-02T20:00'), chanMayIn: T('2026-11-03T06:00'), chanMayOut: T('2026-11-03T09:00'), xpplR: T('2026-11-04T07:00') }];
const apiA = build(plA, sqA, { rows: [] });
const mA = apiA.run('2026-11-01', '2026-11-05');
const RA = mA.cpsR['Mine : A Ngo'];
check('A Ngo 30 min after plan: on time, at A Ngo', RA.ango, { ok: 1, n: 1 });
check('border home after A Ngo counts as border, empty (02:00: outside 07-19)', RA.borderb, { ok: 0, n: 1 });
check('a Mine : A Ngo truck is not judged at the port or QL49', [RA.port, RA.ql49], [{ ok: 0, n: 0 }, { ok: 0, n: 0 }]);
check('...the one that went to the port is off route', [mA.offR['Mine : A Ngo'].n, mA.offR['Mine : A Ngo'].where], [1, { port: 1 }]);
check('the page says so', /went to the port instead/.test(apiA.scDraw(mA, null)), true);
check('one total per route: the planned trucks that came (A1, C3)', mA.cameR['Mine : A Ngo'], 2);
apiA.setRoute('Mine : A Ngo');
const oSame = apiA.scDraw(mA, null).split('Where the schedule slips')[1].split('Average travel')[0];
apiA.setRoute('');
check('every circle out of the same 2: A Ngo 1 on time, 0 late, no data 1 (50%)',
      /A Ngo<\/div>.*?1 on time <span class="sclate">· 0 late<\/span><\/div><div class="scnod">no data 1 \(50%\)/.test(oSame), true);
check('ring parts: on time always green, late red, no data grey (never two reds)',
      (() => { const r = (oSame.split('A Ngo</div>')[0].split('<svg').pop()) || ''; return r.includes('stroke="#34d399"'); })(), true);
check('...arrive mine: 2 on time, nothing missing', /Arrive mine<\/div>.*?2 on time <span class="sclate">· 0 late<\/span><\/div><div class="scnod">no data 0 \(0%\)/.test(oSame), true);

console.log('\nthe page');
const S = api.scSummary(api.run('2026-11-01', '2026-11-05'));
check('headline figures', [S.cameP, S.onP, S.lost, S.quickP, S.recMed, S.bhPlan], [50, 50, 1, 100, 2, 2.5]);
const m0r = api.run('2026-11-01', '2026-11-05');
const out = api.scDraw(m0r, null);
check('draws the four steps', ['Did the plan happen?', 'Where the schedule slips', 'Average travel / time spending by location',
      'Unloaded, back to the mine', 'Opportunity lost'].every(t => out.includes(t)), true);
check('front haul and back haul rows in 3.1', out.includes('Front haul') && out.includes('Back haul'), true);
console.log('\n3.2 the location diagram (as on Performance)');
check('Mine, Border, Port with the Performance plan targets', out.includes('<span class="tnt">Mine</span>') &&
      out.includes('<span class="tnt">Port</span>') && out.includes('<span class="tchip plan">16h 00m</span>'), true);
check('...the actual is the average per trip (A1: mine in/out 1h 10m)', /tchip unplan[^>]*>1h 10m</.test(out), true);
apiA.setRoute('Mine : A Ngo');
const o32 = apiA.scDraw(mA, null).split('Average travel')[1] || '';
apiA.setRoute('');
check('Mine : A Ngo picked: Mine, Border, A Ngo - no port', o32.includes('<span class="tnt">A Ngo</span>') && !o32.includes('<span class="tnt">Port</span>'), true);
check('...border to A Ngo 1h 30m, actual only (no target yet)', /travel ↓<\/div><div class="tconnect"><\/div><div class="tchiprow"><span class="tchip unplan"[^>]*>1h 30m</.test(o32), true);
check('...the way home held to the border-to-mine target (5h 00m)', o32.includes('<span class="tchip plan">5h 00m</span>'), true);
check('...the truck that went to the port is not in the averages', !o32.includes('Port'), true);
check('Off-plan, not "Came, not in plan"', out.includes('Off-plan') && !out.includes('Came, not in plan'), true);
check('every date on the axis, dd/mm', out.includes('>01/11</text>') && out.includes('>02/11</text>') && out.includes('>05/11</text>'), true);
check('grey line between days', (out.match(/class="scsep"/g) || []).length >= 4, true);
check('route slicer: A1 counted under its route', m0r.cpsR['Mine : Chan May'].mine, { ok: 1, n: 1 });
check('a plan with no route counts as Mine : Chan May', m0r.cpsR['Mine : Chan May'] && !m0r.cpsR['(no route)'], true);
check('...with a chip per route and All routes', out.includes('data-route="Mine : Chan May"') && out.includes('All routes'), true);
check('Off-plan is a segment of the daily bar (no diamonds)', out.includes('Off-plan') && !/<path d="M/.test(out), true);
check('square bar ends (no rounded corners)', !/rx="2"/.test(out), true);
check('the menu has it', /data-page="score">Scorecard</.test(html), true);
check('the page scrolls inside itself (10/11/2026: no scroll bar)',
      /\[data-page-panel="score"\] \.scwrap\{flex:1 1 auto;min-height:0;overflow-y:auto/.test(html), true);

console.log('\n' + (FAIL ? FAIL + ' FAILED' : 'ALL PASS'));
process.exit(FAIL ? 1 : 0);
