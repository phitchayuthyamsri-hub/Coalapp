// The Process card, drawn from a real-shaped payload in a stub DOM.
//
// Two things a green tick must never say: that a planner planned a day with
// no coal load, or that a day with no coal load is "Complete". Both were
// true of the card on 18/09/2026.
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync('app/templates/flow.html', 'utf8');
const blocks = (html.match(/<script>([\s\S]*?)<\/script>/g) || [])
  .map(b => b.slice(8, -9)).filter(js => !/{%|{{/.test(js));

const el = () => ({innerHTML:'', textContent:'', style:{}, dataset:{},
  classList:{add(){},remove(){},toggle(){}}, addEventListener(){}, appendChild(){},
  querySelector(){return el()}, querySelectorAll(){return []}});
const store = {};
const sandbox = {
  window: {}, console, Date, JSON, Math, Set, Object, Array, setTimeout, clearTimeout,
  setInterval: () => 0, encodeURIComponent, fetch: () => new Promise(() => {}),
  document: {addEventListener(){}, createElement: el, body: el(),
    getElementById(id){ return store[id] || (store[id] = el()); },
    querySelector(sel){ const id = String(sel).replace(/^#/, '');
      return store[id] || (store[id] = el()); },
    querySelectorAll(){ return []; }},
  location: {hash: '', search: ''}, addEventListener(){},
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
try { vm.runInContext(blocks.join('\n'), sandbox, {filename: 'flow.js'}); } catch (e) {}

let fail = 0;
function is(label, got, want){
  const ok = got === want; if (!ok) fail++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(58)
    + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}
const stage = (who, state, note) => ({key: who.toLowerCase(), who, state, note, window: ''});

function drawn(company){
  vm.runInContext('draw(' + JSON.stringify({days: [{date: '2026-09-19', tomorrow: true,
    today: false, companies: [company]}]}) + ')', sandbox);
  return store['body'].innerHTML;
}

console.log('a day with no coal load - the chain stops at the supervisor');
let out = drawn({company: 'Bac Nam', no_load: true,
  no_load_note: 'no truck is due at the mine to load, so there is no plan to issue',
  stages: [stage('Subcontractor','done','20 trucks declared'),
           stage('Supervisor','done','20 sent'),
           stage('Manager','none','nothing to approve - no coal load'),
           stage('Planner','none','nothing to plan - no truck is due at the mine'),
           stage('Monitor','none','nothing to watch')],
  now: {who: '', note: 'nothing to plan - no truck is due at the mine'}});
is('the banner is on the card', /class="noload"/.test(out), true);
is('...leading with the fact', /<b>No coal load on 19\/09\/2026<\/b>/.test(out), true);
is('...and the reason', out.indexOf('no truck is due at the mine to load') >= 0, true);
is('...above the chain, not under it',
   out.indexOf('class="noload"') < out.indexOf('class="steps'), true);
is('the planner is a dash, not a tick', /s-none[^>]*>[\s\S]*?<div class="dot">—<\/div>[\s\S]*?Planner/.test(out), true);
is('...and its rail is not green', (out.match(/p-done/g) || []).length, 2);
is('nobody is pending', out.indexOf('Pending at') >= 0, false);
is('the rail is greyed for the whole chain', /class="steps noload"/.test(out), true);
is('...and it does not read Complete either', out.indexOf('Complete') >= 0, false);

console.log('\nthe same day once the manager has approved');
out = drawn({company: 'Bac Nam', no_load: true,
  no_load_note: 'no truck is due at the mine to load, so there is no plan to issue',
  stages: [stage('Subcontractor','done',''), stage('Supervisor','done',''),
           stage('Manager','done','20 approved, 0 denied'),
           stage('Planner','none','nothing to plan'), stage('Monitor','none','nothing to watch')],
  now: {who: '', note: 'nothing to plan - no truck is due at the mine'}});
is('it never reads Complete', out.indexOf('Complete') >= 0, false);
is('...the banner is the headline', /class="noload"/.test(out), true);
is('three desks ticked, two dashed',
   [(out.match(/s-done/g) || []).length, (out.match(/s-none/g) || []).length].join('/'), '3/2');
is('the rail is grey here too', /class="steps noload"/.test(out), true);

console.log('\na normal day is unchanged');
out = drawn({company: 'Bac Nam', no_load: false, no_load_note: '',
  stages: [stage('Subcontractor','done',''), stage('Supervisor','done',''),
           stage('Manager','done',''), stage('Planner','done','plan issued'),
           stage('Monitor','done','the day is live on Monitor')],
  now: {who: '', note: 'the whole chain has run'}});
is('no banner', /class="noload"/.test(out), false);
is('it reads Complete', out.indexOf('<b>Complete</b>') >= 0, true);
is('no dashes', /s-none/.test(out), false);
is('the rail is green', /class="steps noload"/.test(out), false);
is('a stage with no time shows none', /class="at/.test(out), false);

// When each desk actually did it (02/10/2026): the window is when it was due.
console.log('\nthe time each desk did its part');
const timed = (who, key, at, by, late, first) => Object.assign(stage(who, 'done', ''),
  {key, at, by, late_min: late, first_at: first});
out = drawn({company: 'Bac Nam', no_load: false, no_load_note: '',
  stages: [timed('Subcontractor', 'declare', '2026-10-02 11:35', 'khanh@bacnamltd.com', 0, '2026-10-02 09:10'),
           timed('Supervisor', 'submit', '2026-10-02 13:40', 'anh.lp@nam-tien.vn', 0),
           timed('Manager', 'approve', '2026-10-02 16:12', 'tuan.hh@nam-tien.vn', 72),
           timed('Planner', 'plan', '2026-10-02 16:05', 'PhitchayuthYamsri', 0),
           stage('Monitor', 'done', 'the day is live on Monitor')],
  now: {who: '', note: 'the whole chain has run'}});
is('the company: declared, day first, 24 h', out.indexOf('declared 02/10 11:35') >= 0, true);
is('...by the name before the @', out.indexOf('&middot; khanh</span>') >= 0, true);
is('...the first filing is on hover', out.indexOf('first filed 02/10 09:10') >= 0, true);
is('the supervisor: submitted', out.indexOf('submitted 02/10 13:40') >= 0, true);
is('the manager: approved, and how late', /approved 02\/10 16:12[\s\S]{0,80}?1 h 12 m late/.test(out), true);
is('...in the late colour, alone', (out.match(/class="at late"/g) || []).length, 1);
is('the planner: issued', out.indexOf('issued 02/10 16:05') >= 0, true);
is('four desks carry a time, the monitor none', (out.match(/class="at/g) || []).length, 4);

console.log(fail ? '\n  ' + fail + ' FAILING' : '\n  all pass');
process.exit(fail ? 1 : 0);
