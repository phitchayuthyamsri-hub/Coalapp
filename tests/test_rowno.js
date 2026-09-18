// The row-number column, on its own and on the two pages that have no row test
// of their own yet: the manager's approvals cards and the planner's tables.
//
// These tables are plain string concatenation, so the fault they invite is a
// header added without its cell (or the other way round) - the whole table
// shifts one column and every heading names the wrong thing. That is what the
// per-page checks below are for.
const fs = require('fs'), vm = require('vm');

let fail = 0;
function is(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fail++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(56)
    + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}
const nos = h => (h.match(/<td class="c-no">(\d+)<\/td>/g) || [])
  .map(s => s.replace(/\D/g, '')).join(',');

// ── rowno.js on its own ────────────────────────────────────────────────────
console.log('\n  rowno.js');
{
  const g = {};
  vm.runInNewContext(fs.readFileSync('app/static/rowno.js', 'utf8'), {window: g});
  is('off the sandbox the header is nothing', g.noHead(), '');
  is('...and so is the cell', g.rowNo(0), '');
  g.STAGING = true;
  is('on the sandbox the header is a plain th',
     g.noHead(), '<th class="c-no" title="Row number, as shown">No#</th>');
  is('...carrying no data-col, so no menu opens', /data-col|data-c=/.test(g.noHead()), false);
  is('the first row reads 1, not 0', g.rowNo(0), '<td class="c-no">1</td>');
  is('the tenth row reads 10', g.rowNo(9), '<td class="c-no">10</td>');
  is('a two-row header spans both',
     g.noHead2(), '<th class="c-no" rowspan="2" title="Row number, as shown">No#</th>');
  is('the flag is read at call time, not at load', (function(){
      g.STAGING = false; return g.rowNo(3);
    })(), '');
}

// ── a stub DOM the two pages can draw into ─────────────────────────────────
function mkSandbox(file, extra){
  const html = fs.readFileSync(file, 'utf8');
  const blocks = (html.match(/<script>([\s\S]*?)<\/script>/g) || [])
    .map(b => b.slice(8, -9)).filter(js => !/{%|{{/.test(js));
  const el = () => ({innerHTML:'', value:'', textContent:'', style:{}, dataset:{},
    checked:false, classList:{add(){},remove(){},toggle(){},contains(){return false}},
    addEventListener(){}, removeEventListener(){}, querySelector(){return el()},
    querySelectorAll(){return []}, appendChild(){}, focus(){}, remove(){},
    getBoundingClientRect(){ return {left:0,top:0,bottom:0,right:0,width:100,height:20}; }});
  const store = {};
  const sandbox = {
    window: {}, console: {log(){}, warn(){}, error(){}},
    document: {addEventListener(){}, createElement: el, body: el(), head: el(),
      documentElement: {style: {setProperty(){}, removeProperty(){}}},
      getElementById(id){ return store[id] || (store[id] = el()); },
      querySelector(sel){
        if (typeof sel === 'string' && sel.charAt(0) === '#'){
          const id = sel.slice(1);
          return store[id] || (store[id] = el());
        }
        return el();
      },
      querySelectorAll(){ return []; }},
    setTimeout, clearTimeout, setInterval: () => 0, clearInterval: () => {},
    Date, Math, JSON, Set, Map, Object, Array, String, Number, Boolean, isNaN,
    parseInt, parseFloat, Promise, RegExp, Error,
    requestAnimationFrame: fn => fn(), encodeURIComponent, decodeURIComponent,
    navigator: {}, localStorage: {getItem(){return null},setItem(){}},
    location: {search:'', hash:'', href:''}, history: {replaceState(){}},
    addEventListener(){}, removeEventListener(){}, alert(){}, confirm(){return true},
    ResizeObserver: function(){ this.observe = () => {}; this.disconnect = () => {}; },
  };
  Object.assign(sandbox, extra || {});
  sandbox.window = sandbox; sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync('app/static/rowno.js', 'utf8'), sandbox, {filename:'rowno.js'});
  try { vm.runInContext(blocks.join('\n'), sandbox, {filename: file}); }
  catch (e) { /* the boot fetches are expected to fail in here */ }
  return {sandbox, store};
}

// ── the manager's approvals cards ──────────────────────────────────────────
console.log('\n  approvals (manager)');
try {
  const {sandbox, store} = mkSandbox('app/templates/approvals.html', {
    fetch: () => Promise.resolve({ok:true, json: () => Promise.resolve({})}),
  });
  const rows = [
    {plate:'20C10615', state:'applied', status:'BH', load:'Empty', location:'QL49',
     arrive_date:'2026-09-19', arrive_hhmm:'05:00', back_in_service:'', remark:'',
     gps_seen:true, differs:[], gps_km_out:20},
    {plate:'20C10770', state:'applied', status:'FH', load:'Loaded', location:'Lalay border',
     arrive_date:'', arrive_hhmm:'', back_in_service:'', remark:'',
     gps_seen:true, differs:['says QL49'], gps_km_out:null},
    {plate:'20H00789', state:'pending', status:'Maintenance', load:'Empty',
     location:'Workshop', arrive_date:'', arrive_hhmm:'', back_in_service:'2026-09-20',
     remark:'Parts due', gps_seen:false, differs:[]},
  ];
  vm.runInContext('DATA = ' + JSON.stringify({
    waiting: 2,
    lists: [{sub:'Bac Nam', sub_id:1, state:'submitted', rows: rows,
             counts:{applied:2, approved:0, denied:0, pending:1},
             can_decide:true, reject_reason:''}]
  }) + '; draw();', sandbox);

  const off = store['body'].innerHTML;
  is('off the sandbox there is no number column', /c-no/.test(off), false);

  vm.runInContext('window.STAGING = true; draw();', sandbox);
  const on = store['body'].innerHTML;
  is('the header is there once per card', (on.match(/<th class="c-no"/g) || []).length, 1);
  is('...leading the header row', on.indexOf('<thead><tr><th class="c-no"') >= 0, true);
  is('every truck row is numbered', nos(on), '1,2,3');
  is('the number leads the row, before the plate',
     /<tr class="[^"]*">(<td class="c-no">1<\/td>)<td class="plate">/.test(on), true);
  // Header cells and body cells must agree, or every column names the wrong thing.
  const headCount = (on.match(/<th[ >]/g) || []).length;
  const firstRow = on.slice(on.indexOf('<tbody>')).match(/<tr[^>]*>[\s\S]*?<\/tr>/)[0];
  is('the row has exactly as many cells as the header has columns',
     (firstRow.match(/<td[ >]/g) || []).length, headCount);
} catch (e) {
  console.log('  APPROVALS THREW: ' + e.message); fail++;
}

// ── the planner's tables ───────────────────────────────────────────────────
console.log('\n  dispatch planner');
try {
  const REV = {
    summary:{trucks:3, hue:2, ql49:1, mean_cycle:44, worst_cycle:51, over_48:1,
             biggest_queue:'at_port', biggest_queue_hours:9},
    planned_all:3, no_time:[],
    rows:[
      {plate:'20C10615', sub:'Bac Nam', route:'hue', cycle_hours:44, total_wait:6,
       waits:{at_port:4}, t:{}},
      {plate:'20C10770', sub:'Bac Nam', route:'ql49', cycle_hours:51, total_wait:9,
       waits:{at_port:9}, t:{}},
      {plate:'20H01353', sub:'Thanh Dat', route:'hue', cycle_hours:40, total_wait:3,
       waits:{at_port:3}, t:{}},
    ]};
  const VAR = {
    baseline:{week_start:'2026-09-14', scope:'all', issued_by:'planner',
              issued_at:'2026-09-17 16:00'},
    summary:{as_planned:2, moved:1, missing:0, unplanned:0, mean_back:30, factor:null},
    rows:[
      {plate:'20C10615', sub:'Bac Nam', status:'as planned', delta:{}, cycle_delta:0, waits:{}},
      {plate:'20C10770', sub:'Bac Nam', status:'moved', delta:{}, cycle_delta:3,
       waits:{at_port:3}},
    ]};
  const WEEK = {planned_all:3, rows:[
      {plate:'20C10615', sub:'Bac Nam', loop:1, from_plan:true, route:'hue',
       cycle_hours:44, total_wait:6, waits:{at_port:4}, t:{}},
      {plate:'20C10770', sub:'Bac Nam', loop:1, from_plan:false, route:'ql49',
       cycle_hours:51, total_wait:9, waits:{at_port:9}, t:{}},
      {plate:'20H01353', sub:'Thanh Dat', loop:2, from_plan:true, route:'hue',
       cycle_hours:40, total_wait:3, waits:{at_port:3}, t:{}},
      {plate:'20H04412', sub:'Thanh Dat', loop:2, from_plan:true, route:'hue',
       cycle_hours:39, total_wait:2, waits:{at_port:2}, t:{}},
    ]};
  const route = u => u.indexOf('/variance') >= 0 ? VAR
               : u.indexOf('/revision') >= 0 ? REV : {rows: [], dormant: false};
  const {sandbox, store} = mkSandbox('app/templates/dispatch_planner.html', {
    fetch: u => Promise.resolve({ok:true, json: () => Promise.resolve(route(String(u)))}),
    L: undefined,
  });

  const run = async () => {
    vm.runInContext('window.STAGING = false;', sandbox);
    await vm.runInContext('run()', sandbox);
    const off = store['body'].innerHTML;
    is('off the sandbox the issued plan has no number column', /c-no/.test(off), false);

    vm.runInContext('window.STAGING = true;', sandbox);
    await vm.runInContext('run()', sandbox);
    const on = store['body'].innerHTML;
    is('the issued plan is numbered', nos(on), '1,2,3');
    is('...with the header leading the row',
       on.indexOf('<thead><tr><th class="c-no"') >= 0, true);

    await vm.runInContext('loadVariance()', sandbox);
    const v = store['vBody'].innerHTML;
    is('plan-against-actual is numbered', nos(v), '1,2');
    is('...with its own header', /<th class="c-no"/.test(v), true);

    vm.runInContext('drawTable(' + JSON.stringify(WEEK) + ')', sandbox);
    const w = store['wTable'].innerHTML;
    is('the week table is numbered', nos(w), '1,2,3,4');
    is('...with its own header', /<th class="c-no"/.test(w), true);

    // Same column-count check as above, on the widest of the three.
    const headCount = (w.match(/<th[ >]/g) || []).length;
    const firstRow = w.slice(w.indexOf('<tbody>')).match(/<tr[^>]*>[\s\S]*?<\/tr>/)[0];
    is('the week row matches its header column for column',
       (firstRow.match(/<td[ >]/g) || []).length, headCount);
  };
  run().then(done).catch(e => { console.log('  PLANNER THREW: ' + e.message); fail++; done(); });
} catch (e) {
  console.log('  PLANNER THREW: ' + e.message); fail++; done();
}

function done(){
  console.log(fail ? '\n  ' + fail + ' FAILING' : '\n  all pass');
  process.exit(fail ? 1 : 0);
}
