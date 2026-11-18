// The Fleet table (21/10/2026): no Usual route column, empty dates show
// nothing, a Company column (a picker for the admin, text for the rest), and
// the add/remove controls only for the admin.
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync('app/tool/index.html', 'utf8').replace(/\r\n/g, '\n');
const grab = (re, what) => { const m = html.match(re); if (!m) throw new Error('not found: ' + what); return m[0]; };
const src = [
  grab(/function fleetRegisterPlates\(\) \{[\s\S]*?\n\}/, 'fleetRegisterPlates'),
  grab(/function allFleetPlates\(\) \{[\s\S]*?\n\}/, 'allFleetPlates'),
  grab(/function fleetCompanyCell\(r\) \{[\s\S]*?\n\}/, 'fleetCompanyCell'),
  grab(/function fleetRows\(\) \{[\s\S]*?\n\}/, 'fleetRows'),
  grab(/const FLEET_EXPORT_COLS = \[[\s\S]*?\n\];/, 'FLEET_EXPORT_COLS'),
  grab(/function fleetExportAoa\(\) \{[\s\S]*?\n\}/, 'fleetExportAoa'),
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
                 effFrom: '', effTo: '', companyId: '', company: ''},
    '20H01364': {status: 'online', added: Date.parse('2026-09-21'), driver: 'Hidden once', phone: '+8490', gps: 'Viettel',
                 effFrom: '2026-09-01', effTo: '', companyId: 13, company: 'Bac Nam', route: 'Mine : A Ngo : Chan May'}},
    // 99Z99999 is only in the GPS history; 20H01364 was removed once and came back on the register
    fileInfo: {plates: new Set(['20H01469', '99Z99999', '88X88888'])}, hiddenPlates: new Set(['20H01364', '88X88888'])},
  normPlate: s => String(s || '').toUpperCase(),
  tripStats: p => (p === '20H01469' ? {ytd: 12, month: 3, avg: 1.2345} : {ytd: 0, month: 0, avg: 0}), effectiveStatus: () => 'online',
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
is('only the trucks on the register, not every GPS plate', rows().length, 3);
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
is('the register only: no plate the GPS alone has seen', /99Z99999/.test(out), false);
is('...the same count as any other login', rows().length, 3);
is('a truck removed once and back on the register is shown', /20H01364/.test(out), true);
is('the summary counts the register', els.fleetSummary.innerHTML.startsWith('3 trucks'), true);
is('Remove offered', (out.match(/fleet-remove/g) || []).length, 3);
is('the company is a picker', (out.match(/data-k="companyId"/g) || []).length, 3);
is('...with the truck\'s company selected', /<option value="13" selected>Bac Nam<\/option>/.test(out), true);

console.log('\nthe export');
const aoa = vm.runInContext('fleetExportAoa()', sandbox);
const heads = [...html.match(/<thead><tr>\s*<th data-fsort="plate">[\s\S]*?<\/tr><\/thead>/)[0].matchAll(/<th[^>]*>([^<]+)<\/th>/g)].map(m => m[1]).filter(h => h !== 'Action');
is('every column on the page is in the file', heads.filter(h => !aoa[0].includes(h)), []);
is('...plus the route', aoa[0].includes('Route'), true);
is('one row per truck on the register', aoa.length - 1, 3);
is('no GPS-only plate in the file', aoa.some(r => r[0] === '99Z99999'), false);
const row = p => { const r = aoa.find(x => x[0] === p); return Object.fromEntries(aoa[0].map((h, i) => [h, r[i]])); };
is('the values of a truck', row('20H01364'), {'Plate': '20H01364', 'Status': 'Online', 'Driver': 'Hidden once', 'Phone': '+8490', 'Effective From': '2026-09-01', 'Effective To': '',
   'GPS Company': 'Viettel', 'Company': 'Bac Nam', 'Route': 'Mine : A Ngo : Chan May', 'Date added': '2026-09-21', 'Trips YTD': 0, 'Trips this month': 0, 'Avg trips/month': 0});
is('trips as on the page', [row('20H01469')['Trips YTD'], row('20H01469')['Trips this month'], row('20H01469')['Avg trips/month']], [12, 3, 1.2]);
is('the upload still finds GPS Company first', aoa[0].findIndex(h => /gps|provider|company/.test(h.toLowerCase())), aoa[0].indexOf('GPS Company'));
vm.runInContext("STATE.fleetSort = {key: 'plate', dir: -1}", sandbox);
is('the file follows the sort on the page', vm.runInContext('fleetExportAoa()', sandbox)[1][0], '75C11111');
vm.runInContext("STATE.fleetSort = {key: 'plate', dir: 1}", sandbox);

console.log('\nthe status pages');
const all = vm.runInContext('allFleetPlates()', sandbox);
is('a truck on the register is never hidden by an old removal', all.includes('20H01364'), true);
is('a removed GPS-only plate stays removed', all.includes('88X88888'), false);
is('other GPS plates are still looked at there', all.includes('99Z99999'), true);

console.log('\nthe page around it');
is('no Usual route heading', />Usual route</.test(html), false);
is('a Company heading', /data-fsort="company"[^>]*>Company</.test(html), true);
is('add / upload / clear are admin-only',
   ['fleetAddBtn', 'fleetTemplateBtn', 'fleetUploadBtn', 'fleetClearBtn'].every(id =>
     new RegExp('id="' + id + '" data-fleet-admin style="display:none').test(html)), true);
is('an empty date box is drawn blank', /input\.fleet-date\[data-empty="1"\]:not\(:focus\)::-webkit-datetime-edit \{ color: transparent; \}/.test(html), true);

console.log(fail ? '\n  ' + fail + ' FAILING' : '\n  all pass');
process.exit(fail ? 1 : 0);
