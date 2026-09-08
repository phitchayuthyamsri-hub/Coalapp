// Run the board's row renderer against real-shaped rows, in a stub DOM.
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync('app/templates/shift_board.html', 'utf8');
const blocks = (html.match(/<script>([\s\S]*?)<\/script>/g) || [])
  .map(b => b.slice(8, -9)).filter(js => !/{%|{{/.test(js));
const tv = fs.readFileSync('app/static/tableview.js', 'utf8');

const el = () => ({innerHTML:'', value:'', textContent:'', style:{}, dataset:{},
  classList:{add(){},remove(){},toggle(){},contains(){return false}},
  addEventListener(){}, removeEventListener(){}, querySelector(){return el()},
  querySelectorAll(){return []}, appendChild(){}, focus(){}, getBoundingClientRect(){
    return {left:0,top:0,bottom:0,right:0,width:100,height:20}; }});
const store = {};
const sandbox = {
  window: {}, console,
  document: {addEventListener(){}, createElement: el, body: el(),
    documentElement: {style: {setProperty(){}, removeProperty(){}}},
    getElementById(id){ return store[id] || (store[id] = el()); },
    // $('#x') must reach the SAME node as getElementById('x'), or the renderer
    // writes into a throwaway element and the test sees nothing.
    querySelector(sel){
      if (typeof sel === 'string' && sel.charAt(0) === '#'){
        const id = sel.slice(1);
        return store[id] || (store[id] = el());
      }
      return el();
    },
    querySelectorAll(){ return []; }},
  fetch: () => Promise.resolve({json: () => Promise.resolve({}), ok:true}),
  setTimeout, clearTimeout, setInterval: () => 0, Date, Math, JSON, Set, Object, Array,
  encodeURIComponent, navigator: {}, localStorage: {getItem(){return null},setItem(){}},
  location: {search:'', hash:''}, history: {replaceState(){}},
  addEventListener(){}, removeEventListener(){}, alert(){}, confirm(){return true},
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(tv, sandbox, {filename: 'tableview.js'});
// only the declarations, not the boot IIFE that fetches
const body = blocks.join('\n');
try { vm.runInContext(body, sandbox, {filename: 'board.js'}); }
catch (e) { console.log('  load error (expected for boot fetches):', e.message.slice(0, 60)); }

// let/const inside a vm script live in the context's lexical scope, not on the
// global object, so these have to be set from inside it.
const ROWS = JSON.stringify([
  {plate:'20C10615', sub:'Bac Nam', note:'BH', sheet_status:'Empty',
   location:'XPPL Mine', arrive_date:'2026-09-09', arrive:'05:00',
   state:'pending', ready:true, reason:''},
  {plate:'20C10770', sub:'Bac Nam', note:'FH', sheet_status:'Loaded',
   location:'Lalay border', arrive_date:'', arrive:'', state:'pending',
   ready:true, reason:''},
  {plate:'20H00789', sub:'Bac Nam', note:'Maintenance', sheet_status:'Empty',
   location:'Workshop', arrive_date:'', arrive:'', state:'pending',
   ready:false, reason:'18,000 km service'},
  {plate:'20H01353', sub:'Bac Nam', note:'BH', sheet_status:'Empty',
   location:'QL49', arrive_date:'', arrive:'', state:'pending',
   ready:true, reason:''},
  {plate:'20H09999', sub:'Bac Nam', absent:true, state:'absent'}
]);
vm.runInContext(`
  ROLE = 'supervisor';
  LIST = {state:'draft', all:false, can:{edit:true, edit_time:true}, rows: ${ROWS}};
  CAN = LIST.can;
  TV = new TableView({
    cols: [
      {key:'plate', label:'Truck'},
      {key:'status', label:'Status', get: r => r.absent ? 'absent' : (r.note || r.reason || '')},
      {key:'adate', label:'Date', get: r => r.arrive_date || ''}
    ],
    onChange(){}
  });
`, sandbox);

let fail = 0;
function is(label, got, want){
  const ok = got === want;
  if (!ok) fail++;
  console.log((ok?'  PASS  ':'  FAIL  ') + label.padEnd(48)
    + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}

try {
  vm.runInContext('drawRows();', sandbox);
  const html2 = store['listBody'].innerHTML;
  console.log('  renderer ran, produced ' + html2.length + ' chars\n');
  is('Status column shows the declared leg', /class="decl[ "]/.test(html2), true);
  is('FH is shown', html2.indexOf('>FH<') >= 0, true);
  is('Maintenance is shown', html2.indexOf('>Maintenance<') >= 0, true);
  is('a BH with no time is flagged', html2.indexOf('needtime') >= 0, true);
  is('...and says why', html2.indexOf('cannot be planned') >= 0, true);
  is('an FH with no time is NOT flagged',
     (html2.match(/needtime/g) || []).length, 1);
  is('the absent row still renders', html2.indexOf('not on this sheet') >= 0, true);
  is('row indices are the ORIGINAL ones', html2.indexOf('data-i="3"') >= 0, true);
  is('headers are sortable', html2.indexOf('data-col="status"') >= 0, true);
  // sorting must not move an edit onto another truck
  // Descending by status is Maintenance, FH, BH, BH, absent - so the first row
  // on the page is the Maintenance truck, which is row 2 in the data. It must
  // carry data-i="2": the index of ITS truck, not its position on screen.
  vm.runInContext("TV.sortSeq = [{key:'status', asc:false}]; drawRows();", sandbox);
  const sorted = store['listBody'].innerHTML;
  const firstI = (sorted.match(/data-i="(\d+)"/) || [])[1];
  is('a sorted row keeps its own index, not its position', firstI, '2');
  is('a filter hides rows', (function(){
      vm.runInContext("TV.sortSeq = []; TV.filters = {status: new Set(['BH'])}; drawRows();", sandbox);
      // minus the header row
      return (store['listBody'].innerHTML.match(/<tr/g) || []).length - 1;
    })(), 2);
} catch (e) {
  console.log('  RENDERER THREW: ' + e.message);
  fail++;
}
console.log(fail ? '\n  ' + fail + ' FAILING' : '\n  all pass');
process.exit(fail ? 1 : 0);
