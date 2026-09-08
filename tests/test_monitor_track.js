// Run the monitor's plan-against-actual renderer in a stub DOM.
//
// The columns here are built fresh on every draw - four places, a plan and an
// actual each, reversed on the back-haul - so a sort or a filter set on one of
// them has to land on the right pair. That is not something a syntax check can
// tell you, and the last three faults on this page were all of that kind.
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync('app/templates/monitor.html', 'utf8');
const blocks = (html.match(/<script>([\s\S]*?)<\/script>/g) || [])
  .map(b => b.slice(8, -9)).filter(js => !/{%|{{/.test(js));
const tv = fs.readFileSync('app/static/tableview.js', 'utf8');

const el = () => ({innerHTML:'', value:'', textContent:'', style:{}, dataset:{},
  checked:false, classList:{add(){},remove(){},toggle(){},contains(){return false}},
  addEventListener(){}, removeEventListener(){}, querySelector(){return el()},
  querySelectorAll(){return []}, appendChild(){}, focus(){},
  getBoundingClientRect(){ return {left:0,top:0,bottom:0,right:0,width:100,height:20}; }});
const store = {};
const sandbox = {
  window: {}, console,
  document: {addEventListener(){}, createElement: el, body: el(),
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
  fetch: () => Promise.resolve({json: () => Promise.resolve({}), ok:true}),
  setTimeout, clearTimeout, setInterval: () => 0, Date, Math, JSON, Set, Object, Array,
  requestAnimationFrame: fn => fn(), encodeURIComponent, navigator: {},
  localStorage: {getItem(){return null},setItem(){}},
  location: {search:'', hash:''}, history: {replaceState(){}},
  addEventListener(){}, removeEventListener(){}, alert(){}, confirm(){return true},
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(tv, sandbox, {filename: 'tableview.js'});
try { vm.runInContext(blocks.join('\n'), sandbox, {filename: 'monitor.js'}); }
catch (e) { console.log('  load error (expected for boot fetches):', e.message.slice(0, 70)); }

const LOCS = [{key:'mine',label:'Mine'},{key:'border',label:'Border'},
              {key:'ql49',label:'QL49'},{key:'port',label:'Port'}];
// plan, actual, delay - one truck on time, one late, one only estimated,
// and one that has not been seen at all.
function truck(plate, sub, mine){
  const c = (plan, actual, delay, est) => ({plan, actual: actual||null,
    delay: (delay === undefined ? null : delay), estimate: est||null});
  return {plate, sub, phone:'+66817916147', phone_known:false, planned:true,
    drift:0, last_seen:null, enroute:null,
    fh: [mine, c('2026-09-09T08:56',null,null,'2026-09-09T08:56'),
         c('2026-09-09T19:00',null,null,'2026-09-09T19:00'),
         c('2026-09-09T21:56',null,null,'2026-09-09T21:56')],
    bh: [c('2026-09-10T05:00',null,null,'2026-09-10T05:00'),
         c('2026-09-10T03:00',null,null,'2026-09-10T03:00'),
         c('2026-09-10T01:00',null,null,'2026-09-10T01:00'),
         c('2026-09-09T23:00',null,null,'2026-09-09T23:00')]};
}
const cell = (plan, actual, delay, est) => ({plan, actual: actual||null,
  delay: (delay === undefined ? null : delay), estimate: est||null});
const ROWS = [
  truck('20C10615','Bac Nam', cell('2026-09-09T05:00','2026-09-09T05:10', 10)),
  truck('20C10770','Bac Nam', cell('2026-09-09T07:00','2026-09-09T12:00', 300)),
  truck('20H00715','NT',      cell('2026-09-09T06:15', null, null, '2026-09-10T00:40')),
  truck('20H00717','NT',      cell('', null)),
];

vm.runInContext(`
  TOL = 60; LEG = 'fh'; TV = null;
  TRACK = {date:'2026-09-09', rows: ${JSON.stringify(ROWS)},
           locations: ${JSON.stringify(LOCS)}, blind: [], issued: true,
           source: 'plan', not_planned: [], not_planned_count: 0,
           on_time_minutes: 60, summary:{trucks:4}};
`, sandbox);

let fail = 0;
function is(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fail++;
  console.log((ok?'  PASS  ':'  FAIL  ') + label.padEnd(52)
    + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}
const plates = () => (store['track'].innerHTML.match(/class="plate">([^<]+)/g) || [])
  .map(s => s.replace(/.*>/, ''));

try {
  vm.runInContext('drawTrack();', sandbox);
  const out = store['track'].innerHTML;
  console.log('  renderer ran, produced ' + out.length + ' chars\n');
  is('every truck is drawn', plates().length, 4);
  is('last location leads the row',
     out.indexOf('<td class="where"') < out.indexOf('<td class="plate"'), true);
  is('...and is not repeated at the end',
     (out.match(/<td class="where"/g) || []).length, 4);
  is('every row links to that truck trail',
     (out.match(/href="\/truck-trail\?plate=/g) || []).length, 4);
  is('...including the one never seen',
     out.indexOf('truck-trail?plate=20H00717') >= 0, true);
  is('the last-location header comes first',
     out.indexOf('data-col="where"') < out.indexOf('data-col="plate"'), true);
  is('the Plan sub-header is now a menu',
     out.indexOf('data-col="fh:mine:plan"') >= 0, true);
  is('so is Actual', out.indexOf('data-col="fh:port:act"') >= 0, true);
  is('sub-headers keep their own class', /class="hd sub2"/.test(out), true);
  is('the id columns still span both header rows',
     (out.match(/rowspan="2"/g) || []).length, 4);

  // Sorting by the mine's actual: on time (05:10), late (12:00), the estimate
  // that lands after midnight (00:40 on the 10th) and then the blank.
  vm.runInContext("TV.sortSeq = [{key:'fh:mine:act', asc:true}]; drawTrack();", sandbox);
  is('actual sorts by the real timestamp, past midnight',
     plates(), ['20C10615','20C10770','20H00715','20H00717']);

  vm.runInContext("TV.sortSeq = [{key:'fh:mine:act', asc:false}]; drawTrack();", sandbox);
  is('and reverses, with the blank still last',
     plates(), ['20H00715','20C10770','20C10615','20H00717']);

  // The filter offers the words from the key, not fifty-eight clock times.
  vm.runInContext("TV.sortSeq = []; TV.filters = {'fh:mine:act': new Set(['late'])}; drawTrack();",
                  sandbox);
  is('filtering the actual by "late" keeps the late one', plates(), ['20C10770']);
  is('...and says what it hid', store['track'].innerHTML.indexOf('3 truck(s) hidden') >= 0, true);

  vm.runInContext("TV.filters = {'fh:mine:plan': new Set(['05:00'])}; drawTrack();", sandbox);
  is('filtering the plan by its clock', plates(), ['20C10615']);

  // Flip to the back-haul: those columns are not on screen any more, so their
  // filter must not go on hiding rows the footer cannot account for.
  vm.runInContext("LEG = 'bh'; drawTrack();", sandbox);
  is('the other leg does not carry a stale filter', plates().length, 4);
  is('back-haul reads port first',
     store['track'].innerHTML.indexOf('data-col="bh:port:plan"')
     < store['track'].innerHTML.indexOf('data-col="bh:mine:plan"'), true);
} catch (e) {
  console.log('  RENDERER THREW: ' + e.message);
  fail++;
}
console.log(fail ? '\n  ' + fail + ' FAILING' : '\n  all pass');
process.exit(fail ? 1 : 0);
