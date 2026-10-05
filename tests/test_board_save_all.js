// A board save sends every row of the day, not only the rows a filter shows.
//
// 05/10/2026: the supervisor filtered the 06/10 board down to the 7 Repair
// trucks and saved. collectRows() read the checkboxes on screen, so the save
// carried 7 rows, and the server - which replaces the day with what it is
// sent - deleted the other 46. Sent back a minute later from the board's own
// copy, they came without the route the company declared.
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync('app/templates/shift_board.html', 'utf8');
const blocks = (html.match(/<script>([\s\S]*?)<\/script>/g) || [])
  .map(b => b.slice(8, -9)).filter(js => !/{%|{{/.test(js));

// The rendered inputs, by selector. Only row 1 is on screen.
const onScreen = {};
const input = (v, checked) => ({value: v, checked: !!checked});
const el = () => ({innerHTML:'', value:'', textContent:'', style:{}, dataset:{},
  classList:{add(){},remove(){},toggle(){},contains(){return false}},
  addEventListener(){}, querySelector(){return el()}, querySelectorAll(){return []},
  appendChild(){}, getBoundingClientRect(){ return {left:0,top:0,bottom:0,right:0,width:0,height:0}; }});
const store = {};
const sandbox = {
  window: {}, console,
  document: {addEventListener(){}, createElement: el, body: el(),
    documentElement: {style: {setProperty(){}, removeProperty(){}}},
    getElementById(id){ return store[id] || (store[id] = el()); },
    querySelector(sel){
      if (typeof sel === 'string' && sel.charAt(0) === '#')
        return store[sel.slice(1)] || (store[sel.slice(1)] = el());
      return onScreen[sel] || null;
    },
    querySelectorAll(sel){
      return Object.keys(onScreen).filter(k => k.indexOf(sel) === 0).map(k => onScreen[k]);
    }},
  fetch: () => new Promise(() => {}), setTimeout, clearTimeout, setInterval: () => 0,
  Date, Math, JSON, Set, Object, Array, requestAnimationFrame: fn => fn(),
  ResizeObserver: function(){ this.observe = () => {}; }, encodeURIComponent,
  navigator: {}, localStorage: {getItem(){return null}, setItem(){}},
  location: {search:'', hash:''}, history: {replaceState(){}},
  addEventListener(){}, removeEventListener(){}, alert(){}, confirm(){ return true; },
  TV: {view: r => r.map((_, i) => i), cols: [], head(){ return ''; }, wire(){}},
  rowNo: () => '', noHead: () => '',
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
try { vm.runInContext(blocks.join('\n'), sandbox, {filename: 'board.js'}); } catch (e) {}

let fail = 0;
function is(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want); if (!ok) fail++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(58)
    + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}

vm.runInContext('LIST = ' + JSON.stringify({rows: [
  {plate:'20H01469', note:'BH', sheet_status:'Empty', location:'Lalay border',
   arrive_date:'2026-10-06', arrive:'14:30', state:'pending', ready:true, reason:''},
  {plate:'20H01397', note:'Repair', sheet_status:'Empty', location:'Workshop',
   arrive_date:'', arrive:'', state:'pending', ready:true, reason:''},
  {plate:'20H01474', note:'BH', sheet_status:'Empty', location:'QL49',
   arrive_date:'2026-10-06', arrive:'08:00', state:'pending', ready:true, reason:''},
  {plate:'20C21667', absent:true},
]}), sandbox);
// The filter shows the Repair truck only; the supervisor unticks it.
onScreen['.r-ready[data-i="1"]'] = Object.assign(input('', false), {dataset: {i: '1'}});
onScreen['.r-adate[data-i="1"]'] = input('');
onScreen['.r-arrive[data-i="1"]'] = input('');
onScreen['.r-reason[data-i="1"]'] = input(' in the workshop ');

const rows = vm.runInContext('collectRows()', sandbox);
const by = {}; rows.forEach(r => { by[r.plate] = r; });

console.log('a save made with a filter on');
is('every row on the sheet is sent, not the 1 on screen', rows.map(r => r.plate),
   ['20H01469', '20H01397', '20H01474']);
is('...but not a truck that was never on the sheet', '20C21667' in by, false);
is('the row on screen takes what was typed', [by['20H01397'].ready, by['20H01397'].reason],
   [false, 'in the workshop']);
is('a hidden row keeps its tick', by['20H01469'].ready, true);
is('...its declared status', by['20H01469'].activity, 'BH');
is('...and its arrival', [by['20H01474'].arrive_date, by['20H01474'].arrive], ['2026-10-06', '08:00']);

console.log(fail ? '\n  ' + fail + ' FAILING' : '\n  all pass');
process.exit(fail ? 1 : 0);
