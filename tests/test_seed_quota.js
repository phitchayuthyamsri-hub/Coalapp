// The issued plan reaches the tool page even when localStorage is nearly full (20/11/2026).
//
// Run: node tests/test_seed_quota.js
//
// The shared-store pull fills localStorage with ~4.4 million characters
// (weighbridge + GPS timing) before /api/tool/seed.js runs. Writing the whole
// issued plan on top went over the browser's ~5 million limit, setItem threw,
// and the page fell back to a stale team copy of 40 plan rows (07-08/11): the
// Daily page showed nothing planned and every truck as "came, not in plan".
// The plan now travels in memory (window.__TOOL_SEED) and is never stored.
const fs = require('fs'), path = require('path'), vm = require('vm');
const ROOT = path.join(__dirname, '..');
let FAIL = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) FAIL++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(64) + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}

// ---- a localStorage with the browser's quota -----------------------------
const QUOTA = 5 * 1024 * 1024;   // characters, key + value, as Chrome counts
function makeStorage(init) {
  const m = new Map(Object.entries(init));
  const used = () => { let n = 0; for (const [k, v] of m) n += k.length + v.length; return n; };
  return {
    getItem: k => (m.has(k) ? m.get(k) : null),
    setItem(k, v) { v = String(v); const before = m.get(k);
      m.set(k, v); if (used() > QUOTA) { if (before === undefined) m.delete(k); else m.set(k, before);
        const e = new Error('QuotaExceededError'); e.name = 'QuotaExceededError'; throw e; } },
    removeItem: k => m.delete(k),
    get length() { return m.size; }, key: i => [...m.keys()][i],
  };
}

// ---- the seed script, as the server renders it ---------------------------
const py = fs.readFileSync(path.join(ROOT, 'app', 'tool_link.py'), 'utf8');
const SEED_JS = py.match(/SEED_JS = r"""([\s\S]*?)"""/)[1];
const plan = {};
for (let d = 1; d <= 20; d++) for (let t = 0; t < 63; t++) {
  const day = '2026-11-' + String(d).padStart(2, '0'), plate = '20H' + String(1000 + t);
  plan[plate + '|' + day] = { plate, date: day, loadStart: day + 'T06:00', mineArrive: day + 'T06:00', depMine: day + 'T07:00',
    borderArrive: day + 'T10:00', depBorder: day + 'T15:00', portArrive: day + 'T22:00', depPort: day + 'T09:00',
    borderBack: null, mineReturn: day + 'T16:00', route: 'Mine : Chan May', angoArrive: null };
}
// Sizes as measured on prod 20/11/2026: plan 506K, GPS status 456K, declared status 88K, fleet 33K.
const seed = { fleet: { '20H01000': { status: 'online', pad: 'f'.repeat(33000) } }, plan,
  status: { plates: ['20H1000'], dates: [], cell: {}, pad: 's'.repeat(88000) },
  gpsStatus: { plates: [], pad: 'g'.repeat(456000) }, at: '2026-11-20T00:00:00' };
const js = SEED_JS.replace('__SEED__', JSON.stringify(seed)).replace('__FLEET_KEY__', '"actualGpsFleet_v2"')
  .replace('__DIN_KEY__', '"actualGpsDataInput_v1"').replace('__IDB_NAME__', '"actual_gps"')
  .replace('__IDB_VERSION__', '1').replace('__FILE_ID__', '"server:coalapp"');

const stale = { plan: { '20H1000|2026-11-07': { plate: '20H1000', date: '2026-11-07' } }, status: null, manual: { 'X|2026-11-01|mine': 'm' }, assign: { a: 'b' }, wbfill: {} };
const ls = makeStorage({
  actualGpsWeigh_v1: 'w'.repeat(2292430), actualGpsTiming_v1: 't'.repeat(2042214),
  actualGpsDataInput_v1: JSON.stringify(stale),
});
check('server seed would not fit next to the shared store', JSON.stringify(seed).length + 4392424 > QUOTA, true);

const warns = [];
const ctx = { window: {}, localStorage: ls, console: { warn: (...a) => warns.push(a.join(' ')), info() {}, log() {} }, indexedDB: {}, JSON, Promise };
ctx.window.localStorage = ls;
vm.createContext(ctx);
vm.runInContext(js, ctx);
const W = ctx.window;
check('page gets every plan row in memory', Object.keys((W.__TOOL_SEED || {}).plan || {}).length, 1260);
check('seed raised no storage warning', warns, []);
const stored = JSON.parse(ls.getItem('actualGpsDataInput_v1'));
check('stored copy holds no plan (stale 07/11 rows gone)', stored.plan, {});
check('operator manual entries kept', stored.manual, stale.manual);
check('operator assignments kept', stored.assign, stale.assign);
check('weighbridge and timing untouched', [ls.getItem('actualGpsWeigh_v1').length, ls.getItem('actualGpsTiming_v1').length], [2292430, 2042214]);

// ---- the page's own loader and saver -------------------------------------
const html = fs.readFileSync(path.join(ROOT, 'app', 'tool', 'index.html'), 'utf8');
const grab = name => { const i = html.indexOf('function ' + name + '()'); let j = html.indexOf('\n}', i);
  if (name === 'dinSave') j = html.indexOf('} catch (e) {} }', i) + 15; return html.slice(i, j + 2); };
const page = 'const DIN_LS_KEY = "actualGpsDataInput_v1"; var STATE = { din: { plan: {}, weigh: {}, status: null } };'
  + 'function _weighSeed(){ return {}; }\n' + grab('dinSave') + '\n' + grab('dinLoad') + '\n'
  + 'dinLoad(); var afterLoad = { plan: Object.keys(STATE.din.plan).length, status: !!STATE.din.status, gps: !!STATE.din.gpsStatus, manual: JSON.parse(JSON.stringify(STATE.din.manual)) };'
  + 'STATE.din.manual["Y|2026-11-02|port"] = "p"; dinSave();';
const pctx = { window: W, localStorage: ls, JSON, Object };
vm.createContext(pctx);
vm.runInContext(page, pctx);
check('dinLoad: plan comes from the server seed', pctx.afterLoad.plan, 1260);
check('dinLoad: declared and GPS status from the seed', [pctx.afterLoad.status, pctx.afterLoad.gps], [true, true]);
check('dinLoad: manual entries read from storage', pctx.afterLoad.manual, stale.manual);
const saved = JSON.parse(ls.getItem('actualGpsDataInput_v1'));
check('dinSave: plan not written back to storage', saved.plan, {});
check('dinSave: a new manual entry is saved', saved.manual['Y|2026-11-02|port'], 'p');

// Without the seed (a saved offline copy) the page still reads the stored plan.
const ls2 = makeStorage({ actualGpsDataInput_v1: JSON.stringify(stale) });
const octx = { window: {}, localStorage: ls2, JSON, Object };
vm.createContext(octx);
vm.runInContext(page.replace('STATE.din.manual["Y|2026-11-02|port"] = "p"; dinSave();', ''), octx);
check('offline copy (no seed) still reads its stored plan', octx.afterLoad.plan, 1);

console.log(FAIL ? '\n' + FAIL + ' FAILED' : '\nall passed');
process.exit(FAIL ? 1 : 0);
