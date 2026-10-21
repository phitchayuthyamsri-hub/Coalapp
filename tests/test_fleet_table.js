// The Fleet table (21/10/2026): no Usual route column, empty dates show
// nothing, a Company column (a picker for the admin, text for the rest), and
// the add/remove controls only for the admin.
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync('app/tool/index.html', 'utf8').replace(/\r\n/g, '\n');
const grab = (re, what) => { const m = html.match(re); if (!m) throw new Error('not found: ' + what); return m[0]; };
const src = [
  grab(/function fleetCompanyCell\(r\) \{[\s\S]*?\n\}/, 'fleetCompanyCell'),
  grab(/function renderFleetUI\(\) \{[\s\S]*?\n\}\n/, 'renderFleetUI'),
].join('\n');

const els = {};
const el = () => ({innerHTML: '', querySelectorAll(){ return []; }});
const sandbox = {
  FLEET_ADMIN: false, FLEET_SUBS: [{id: 13, short: 'Bac Nam'}, {id: 2, short: 'Hoanh Son'}],
  _routeDefsAsked: true, loadRoutes(){},
  STATE: {fleetSort: {key: 'plate', dir: 1}, routeDefs: [], fleet: {
    '20H01469': {status: 'online', added: Date.parse('2026-09-20'), driver: 'Loc', phone: '+8486', gps: 'Viettel',
                 effFrom: '2026-09-09', effTo: '', companyId: 13, company: 'Bac Nam'},
    '75C11111': {status: 'online', added: null, driver: '', phone: '', gps: 'TCT',
                 effFrom: '', effTo: '', companyId: '', company: ''}}},
  allFleetPlates: () => ['20H01469', '75C11111', '99Z99999'],     // the last only the GPS knows
  tripStats: () => ({ytd: 0, month: 0, avg: 0}), effectiveStatus: () => 'online',
  statusPill: s => s, FLEET_STATUSES: ['online'], FLEET_STATUS_LABEL: {online: 'Online'},
  isoDate: d => d.toISOString().slice(0, 10), escapeHtml: s => String(s == null ? '' : s),
  document: {getElementById: id => els[id] || (els[id] = el())},
};
vm.createContext(sandbox);
vm.runInContext(src, sandbox);

let fail = 0;
function is(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want); if (!ok) fail++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(58)
    + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}
const rows = () => els.fleetBody.innerHTML.split('<tr>').slice(1);

console.log('a subcontractor login');
vm.runInContext('renderFleetUI()', sandbox);
let out = els.fleetBody.innerHTML;
is('only the trucks it was given, not every GPS plate', rows().length, 2);
is('no Remove button', /fleet-remove/.test(out), false);
is('the company is text, not a picker', /data-k="companyId"/.test(out), false);
is('...reading Bac Nam', /<td>Bac Nam<\/td>/.test(out), true);
is('no route cell', /fleetRouteCell|route/.test(out.replace(/data-k="(driver|phone|gps|effFrom|effTo)"/g, '')), false);
is('an empty date is marked empty (drawn blank)', /data-empty="1" data-plate="75C11111" data-k="effFrom"/.test(out), true);
is('...a set one is not', /data-empty="" data-plate="20H01469" data-k="effFrom" value="2026-09-09"/.test(out), true);
is('no "-> Now" beside an open end', /Now/.test(out), false);

console.log('\nthe admin');
vm.runInContext('FLEET_ADMIN = true; renderFleetUI()', sandbox);
out = els.fleetBody.innerHTML;
is('every plate, as before', rows().length, 3);
is('Remove offered', (out.match(/fleet-remove/g) || []).length, 3);
is('the company is a picker', (out.match(/data-k="companyId"/g) || []).length, 3);
is('...with the truck\'s company selected', /<option value="13" selected>Bac Nam<\/option>/.test(out), true);

console.log('\nthe page around it');
is('no Usual route heading', />Usual route</.test(html), false);
is('a Company heading', /data-fsort="company"[^>]*>Company</.test(html), true);
is('add / upload / clear are admin-only',
   ['fleetAddBtn', 'fleetTemplateBtn', 'fleetUploadBtn', 'fleetClearBtn'].every(id =>
     new RegExp('id="' + id + '" data-fleet-admin style="display:none').test(html)), true);
is('an empty date box is drawn blank', /input\.fleet-date\[data-empty="1"\]:not\(:focus\)::-webkit-datetime-edit \{ color: transparent; \}/.test(html), true);

console.log(fail ? '\n  ' + fail + ' FAILING' : '\n  all pass');
process.exit(fail ? 1 : 0);
