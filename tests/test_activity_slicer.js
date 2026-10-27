// The Activity page: pick users with checkboxes and compare them (27/10/2026).
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync('app/templates/activity.html', 'utf8');
const js = (html.match(/<script>([\s\S]*?)<\/script>/g) || []).map(b => b.slice(8, -9)).join('\n')
  .replace(/fetch\('\/api\/admin\/activity'\)[\s\S]*$/, '');      // the boot call, not the functions

const els = {};
const el = () => ({innerHTML: '', textContent: '', value: '', addEventListener(){}, focus(){}, setSelectionRange(){}});
const sandbox = {
  document: {getElementById: id => els[id] || (els[id] = el()), querySelectorAll: () => [], querySelector: () => el()},
  localStorage: {getItem(){ return null; }, setItem(){}}, Intl, Date, JSON, Math, Set, Object, Array, String,
};
vm.createContext(sandbox);
vm.runInContext(js, sandbox);

let fail = 0;
function is(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want); if (!ok) fail++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(58)
    + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}
const user = (areas, logins, sends) => ({total_seconds: areas.reduce((s, a) => s + a[1], 0),
  areas: areas.map(a => ({page: a[0], seconds: a[1]})), countries: [{code: 'VN', country: 'Vietnam', count: logins}],
  logins: [], events: [], whatsapp: {sends: sends, chats: 0}});
vm.runInContext('DATA = ' + JSON.stringify({
  'hoang.ph@nam-tien.vn': user([['ops:monitor', 7200], ['send', 600]], 9, 5),
  'anh.lp@nam-tien.vn': user([['ops:readiness', 3600], ['ops:monitor', 60]], 4, 0),
  'huytrv@bacnamltd.com': user([['ops:subcontractor', 900]], 2, 0)}) + ';'
  + "NAMES = Object.keys(DATA); SEL = new Set(['hoang.ph@nam-tien.vn', 'anh.lp@nam-tien.vn']); drawAll();", sandbox);

const cmp = els.cmp.innerHTML, list = els.list.innerHTML, sl = els.slicer.innerHTML;
console.log('two users ticked');
is('every user is offered as a checkbox', (sl.match(/type="checkbox"/g) || []).length, 3);
is('...the two chosen are ticked', (sl.match(/ checked>/g) || []).length, 2);
is('the comparison has a column each', (cmp.match(/<th title=/g) || []).length, 2);
is('...a row per area either of them used', /Ops › Monitor/.test(cmp) && /Ops › Supervisor/.test(cmp) && /Send Plan/.test(cmp), true);
is('...the larger value is marked', /<td class="top">2h 0m/.test(cmp), true);
is('an area one never used reads as a dash', /<td class="zero">—<\/td>/.test(cmp), true);
is('only their two cards are listed', (list.match(/class="uname"/g) || []).length, 2);
vm.runInContext("SEL = new Set(['huytrv@bacnamltd.com']); drawAll();", sandbox);
is('one user ticked: no comparison table', els.cmp.innerHTML, '');
console.log(fail ? '\n  ' + fail + ' FAILING' : '\n  all pass');
process.exit(fail ? 1 : 0);
