// Run the board's row renderer against real-shaped rows, in a stub DOM.
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync('app/templates/shift_board.html', 'utf8');
const blocks = (html.match(/<script>([\s\S]*?)<\/script>/g) || [])
  .map(b => b.slice(8, -9)).filter(js => !/{%|{{/.test(js));
const tv = fs.readFileSync('app/static/tableview.js', 'utf8');
const rowno = fs.readFileSync('app/static/rowno.js', 'utf8');

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
  requestAnimationFrame: fn => fn(), ResizeObserver: function(){ this.observe = () => {}; },
  encodeURIComponent, navigator: {}, localStorage: {getItem(){return null},setItem(){}},
  location: {search:'', hash:''}, history: {replaceState(){}},
  addEventListener(){}, removeEventListener(){}, alert(){}, confirm(){return true},
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(tv, sandbox, {filename: 'tableview.js'});
vm.runInContext(rowno, sandbox, {filename: 'rowno.js'});
// only the declarations, not the boot IIFE that fetches
const body = blocks.join('\n');
try { vm.runInContext(body, sandbox, {filename: 'board.js'}); }
catch (e) { console.log('  load error (expected for boot fetches):', e.message.slice(0, 60)); }

// let/const inside a vm script live in the context's lexical scope, not on the
// global object, so these have to be set from inside it.
const ROWS = JSON.stringify([
  {plate:'20C10615', sub:'Bac Nam', note:'BH', sheet_status:'Empty',
   location:'XPPL Mine', arrive_date:'2026-09-09', arrive:'05:00',
   state:'pending', ready:true, reason:'',
   gps_loc:'Chan May port', gps_seen:'2026-09-15 10:19', gps_km:116.9},
  {plate:'20C10770', sub:'Bac Nam', note:'FH', sheet_status:'Loaded',
   location:'Lalay border', arrive_date:'', arrive:'', state:'pending',
   ready:true, reason:'', gps_loc:'Lalay border', gps_seen:'2026-09-15 11:15'},
  {plate:'20H00789', sub:'Bac Nam', note:'Maintenance', sheet_status:'Empty',
   location:'Workshop', arrive_date:'', arrive:'', state:'pending',
   ready:false, reason:'18,000 km service',
   back_in_service:'2026-09-18', remark:'Parts due Thursday'},
  {plate:'20H01353', sub:'Bac Nam', note:'BH', sheet_status:'Empty',
   location:'QL49', arrive_date:'', arrive:'', state:'pending',
   ready:true, reason:'', gps_loc:'On the road', gps_seen:'2026-09-15 21:08',
   gps_road:'QL49 > Chan May port', gps_km:116.9},
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
  is('the declared back-in-service date is shown',
     html2.indexOf('18/09/2026') >= 0, true);
  is('the company remark is shown', html2.indexOf('Parts due Thursday') >= 0, true);
  is('the reason is a wrapping box, not a one-line input',
     /<textarea class="r-reason"[^>]*>18,000 km service<\/textarea>/.test(html2), true);
  is('no input carries a fixed inline width', /style="width:(150|110)px"/.test(html2), false);
  is('the trail has its own column', /<td class="c-trail"> <a class="trail"/.test(html2), true);
  is('...on the absent row too',
     /20H09999<\/td><td class="c-trail"> <a class="trail"/.test(html2), true);
  is('the truck cell no longer holds the link',
     /<td class="plate">[^<]*<a class="trail"/.test(html2), false);
  is('the trail header has no sort menu', html2.indexOf('<th class="c-trail">Trail</th>') >= 0, true);
  is('the absent row still spans the table', html2.indexOf('colspan="8"') >= 0, true);
  is('a GPS place matching the declaration is shown',
     html2.indexOf('<span class="gps-loc">Lalay border</span>') >= 0, true);
  is('a mismatch reads Unknown', html2.indexOf('<span class="gps-loc">Unknown</span>') >= 0, true);
  is('...with the GPS place kept in the tooltip',
     html2.indexOf('GPS last saw it at Chan May port') >= 0, true);
  is('the Status header carries no hint', html.indexOf('FH / BH / why not') < 0, true);
  is('...with when it was seen and km to the mine',
     html2.indexOf('2026-09-15 10:19 &middot; 116.9 km to mine') >= 0, true);
  is('GPS elsewhere than declared is flagged', html2.indexOf('gps-diff') >= 0, true);
  is('between checkpoints the stretch of road is named',
     html2.indexOf('<span class="gps-loc">QL49 &gt; Chan May port</span>') >= 0, true);
  is('...and a bare On the road is never shown',
     html2.indexOf('>On the road<') >= 0, false);
  is('a road segment does not read as a mismatch',
     /QL49 &gt; Chan May port[\s\S]{0,200}gps-diff/.test(html2)
       || /gps-diff[^>]*>[^<]*<span class="gps-loc">QL49/.test(html2), false);
  is('a truck GPS never saw says so', html2.indexOf('no GPS') >= 0, true);
  is('...with no explanation beside it',
     /<span class="gps-none">no GPS<\/span><\/td>/.test(html2), true);
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

  // The No# column: staging only, and it numbers what is ON SCREEN. A filtered
  // table that still read 1, 4, 5 would be a worse answer to "which one am I
  // on" than no column at all.
  is('off the sandbox there is no No# column', html2.indexOf('c-no') >= 0, false);
  vm.runInContext("TV.filters = {}; window.STAGING = true; drawRows();", sandbox);
  const numbered = store['listBody'].innerHTML;
  is('on the sandbox the No# header is there',
     numbered.indexOf('<th class="c-no"') >= 0, true);
  is('...with no sort menu on it', /<th class="c-no"[^>]*data-col/.test(numbered), false);
  is('...and it is the first column',
     numbered.indexOf('<tbody><tr><td class="c-no">1</td><td class="plate">') >= 0, true);
  is('every row is numbered, absent ones included',
     (numbered.match(/<td class="c-no">/g) || []).length, 5);
  is('the absent row is numbered too',
     /<tr style="opacity:.72"><td class="c-no">5<\/td>/.test(numbered), true);
  is('...and still spans the rest of the table', numbered.indexOf('colspan="8"') >= 0, true);
  is('numbering follows the sort, not the data order', (function(){
      vm.runInContext("TV.sortSeq = [{key:'status', asc:false}]; drawRows();", sandbox);
      // Maintenance sorts first; it must be No# 1 while keeping data-i="2".
      return /<td class="c-no">1<\/td><td class="plate">20H00789/.test(
        store['listBody'].innerHTML);
    })(), true);
  is('a filtered table renumbers from 1', (function(){
      vm.runInContext(
        "TV.sortSeq = []; TV.filters = {status: new Set(['BH'])}; drawRows();", sandbox);
      const h = store['listBody'].innerHTML;
      return (h.match(/<td class="c-no">(\d+)<\/td>/g) || []).join(',');
    })(), '<td class="c-no">1</td>,<td class="c-no">2</td>');
} catch (e) {
  console.log('  RENDERER THREW: ' + e.message);
  fail++;
}
console.log(fail ? '\n  ' + fail + ' FAILING' : '\n  all pass');
process.exit(fail ? 1 : 0);
