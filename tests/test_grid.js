// Runs grid.js against a stub table: no rendering, just the behaviour that
// replaces the drop-downs.
const fs = require('fs'), vm = require('vm');
const cells = {};
function fakeTable(){
  return {
    innerHTML: '', dataset: {},
    setAttribute(){}, focus(){},
    addEventListener(){}, removeEventListener(){},
    querySelector(sel){
      const m = sel.match(/data-r="(\d+)"\]\[data-c="(\d+)"/);
      if (!m) return null;
      const k = m[1]+','+m[2];
      cells[k] = cells[k] || {dataset:{r:m[1],c:m[2]}, classList:{toggle(){},add(){},remove(){}},
                              innerHTML:'', scrollIntoView(){}};
      return cells[k];
    },
    querySelectorAll(){ return []; }
  };
}
const sandbox = {window:{}, document:{addEventListener(){}}, navigator:{}, Date, Math, console};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('app/static/grid.js','utf8'), sandbox, {filename:'grid.js'});
const Grid = sandbox.window.Grid;

const STATUS = ['FH','BH','Maintenance','Breakdown','Repair','Accident','No driver',
                'Standby','Paperwork hold','Not available'];
const cols = [
  {key:'plate', label:'Truck', ro:true},
  {key:'status', label:'Status', list:STATUS},
  {key:'load', label:'Load', list:['Loaded','Empty']},
  {key:'remark', label:'Remark'}
];
function mk(n){
  return Array.from({length:n}, (_,i) => ({plate:'20C'+(1000+i), status:'', load:'', remark:''}));
}
function g(rows){
  const gr = new Grid({table: fakeTable(), cols, rows});
  gr.draw = () => {}; gr.refreshRow = () => {}; gr.paint = () => {};
  return gr;
}
let fail = 0;
function is(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fail++;
  console.log((ok?'  PASS  ':'  FAIL  ') + label.padEnd(46)
    + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}

// type-ahead: the thing that replaces the click
let gr = g(mk(5));
gr.cur = {r:0,c:1}; gr.anchor = {r:0,c:1};
gr.typeAhead('f');
is('type f  -> FH', gr.rows[0].status, 'FH');
gr.cur = {r:1,c:1}; gr.typeBuf=''; gr.typeAt = 0;
gr.typeAhead('b');
is('type b  -> BH', gr.rows[1].status, 'BH');
gr.typeAhead('b');                      // same letter again, within the window
is('b again -> Breakdown', gr.rows[1].status, 'Breakdown');
gr.cur = {r:2,c:1}; gr.typeBuf=''; gr.typeAt=0;
gr.typeAhead('m');
is('type m  -> Maintenance', gr.rows[2].status, 'Maintenance');
gr.cur = {r:3,c:1}; gr.typeBuf=''; gr.typeAt=0;
gr.typeAhead('n'); 
is('type n  -> No driver', gr.rows[3].status, 'No driver');
gr.typeAhead('n');
is('n again -> Not available', gr.rows[3].status, 'Not available');

// only allowed values land
gr = g(mk(3));
is('set a bad value is refused', gr.set(0,1,'Banana'), false);
is('...and nothing was written', gr.rows[0].status, '');
is('case-insensitive is accepted', gr.set(0,1,'fh'), true);
is('...normalised to the list value', gr.rows[0].status, 'FH');
is('read-only column refused', gr.set(0,0,'X'), false);

// fill down: one row selected fills to the bottom
gr = g(mk(6));
gr.rows[0].status = 'BH';
gr.cur = {r:0,c:1}; gr.anchor = {r:0,c:1};
gr.fillDown();
is('Ctrl+D from one row fills to the end',
   gr.rows.map(r=>r.status), ['BH','BH','BH','BH','BH','BH']);

// fill down inside a selection stops at the selection
gr = g(mk(6));
gr.rows[1].status = 'FH';
gr.anchor = {r:1,c:1}; gr.cur = {r:3,c:1};
gr.fillDown();
is('Ctrl+D in a block stays in the block',
   gr.rows.map(r=>r.status), ['','FH','FH','FH','','']);

// paste a block straight out of Excel
gr = g(mk(4));
gr.cur = {r:0,c:1}; gr.anchor = {r:0,c:1};
let res = gr.paste('FH\tLoaded\tgoing out\nBH\tEmpty\tcoming back\n');
is('paste 2x3 block lands', [gr.rows[0].status, gr.rows[0].load, gr.rows[0].remark,
                             gr.rows[1].status, gr.rows[1].load, gr.rows[1].remark],
   ['FH','Loaded','going out','BH','Empty','coming back']);
is('paste counts accepted cells', res.ok, 6);

gr = g(mk(3));
gr.cur = {r:0,c:1}; gr.anchor = {r:0,c:1};
res = gr.paste('FH\nrubbish\nBH\n');
is('a bad value is rejected, not written', gr.rows[1].status, '');
is('...and reported', [res.ok, res.bad], [2,1]);

// copy gives Excel-shaped text
gr = g(mk(3));
gr.rows[0].status='FH'; gr.rows[0].load='Loaded';
gr.rows[1].status='BH'; gr.rows[1].load='Empty';
gr.anchor={r:0,c:1}; gr.cur={r:1,c:2};
is('copy is tab separated', gr.copyText(), 'FH\tLoaded\nBH\tEmpty');

// clear
gr = g(mk(3));
gr.rows[0].status='FH'; gr.rows[1].status='BH';
gr.anchor={r:0,c:1}; gr.cur={r:1,c:1};
gr.clear();
is('Delete clears the selection', [gr.rows[0].status, gr.rows[1].status], ['','']);


// ── sort, filter, and the trap they bring with them ────────────────────────
console.log('');
gr = g(mk(5));
gr.rows[0].status='Repair'; gr.rows[1].status='FH'; gr.rows[2].status='BH';
gr.rows[3].status=''; gr.rows[4].status='Accident';
gr.sort = {c:1, dir:'asc'}; gr.applyView();
is('sort asc orders by value',
   gr.view.map(i=>gr.rows[i].status), ['Accident','BH','FH','Repair','']);
gr.sort = {c:1, dir:'desc'}; gr.applyView();
is('sort desc reverses, blanks still last',
   gr.view.map(i=>gr.rows[i].status), ['Repair','FH','BH','Accident','']);
gr.sort = null; gr.applyView();
is('third click restores the original order', gr.view, [0,1,2,3,4]);

gr = g(mk(5));
gr.rows[0].status='FH'; gr.rows[1].status='BH'; gr.rows[2].status='FH';
gr.rows[3].status=''; gr.rows[4].status='BH';
gr.filters = {status:'FH'}; gr.applyView();
is('filter to one value', gr.view, [0,2]);
gr.filters = {status:'\u2205'}; gr.applyView();
is('the (blank) filter finds unanswered rows', gr.view, [3]);
gr.filters = {}; gr.applyView();
is('clearing the filter shows everything', gr.view.length, 5);

gr = g(mk(4));
gr.rows[0].remark='gearbox'; gr.rows[1].remark='TYRE'; gr.rows[2].remark='gear box';
gr.filters = {remark:'gear'}; gr.applyView();
is('text filter is contains, case-insensitive', gr.view, [0,2]);

// THE TRAP: with a sort on, view position 0 is not row 0. An edit must follow
// the truck, not the screen position.
gr = g(mk(3));
gr.rows[0].plate='20C1000'; gr.rows[1].plate='20C1001'; gr.rows[2].plate='20C1002';
gr.rows[0].status='Repair'; gr.rows[1].status='BH'; gr.rows[2].status='FH';
gr.sort = {c:1, dir:'asc'}; gr.applyView();     // BH, FH, Repair -> rows 1,2,0
is('sorted view maps to the right rows', gr.view, [1,2,0]);
gr.cur = {r:0,c:3}; gr.anchor = {r:0,c:3};
gr.set(0, 3, 'edited');
is('editing the top sorted row hits ITS truck', gr.rows[1].remark, 'edited');
is('...and not the first row on the page', gr.rows[0].remark, '');

// filtered fill-down must not touch hidden rows
gr = g(mk(5));
gr.rows[0].status='FH'; gr.rows[1].status='BH'; gr.rows[2].status='FH';
gr.rows[3].status='BH'; gr.rows[4].status='FH';
gr.filters = {status:'FH'}; gr.applyView();      // rows 0,2,4
gr.cur={r:0,c:3}; gr.anchor={r:0,c:3};
gr.rows[0].remark='out';
gr.fillDown();
is('fill-down fills only what is on screen',
   gr.rows.map(r=>r.remark||''), ['out','','out','','out']);

// ── time normalising ───────────────────────────────────────────────────────
console.log('');
const nt = sandbox.window.Grid.normTime;
[['6','06:00'],['600','06:00'],['6:00','06:00'],['6.00','06:00'],['0600','06:00'],
 ['18:30','18:30'],['1830','18:30'],['23:59','23:59'],['',''],
 ['25:00',null],['12:75',null],['abc',null],['9:5',null]
].forEach(([inp,want]) => is('time "'+inp+'"', nt(inp), want));

gr = g([{plate:'x',status:'',load:'',remark:'',time:''}]);
gr.cols = gr.cols.concat([{key:'time',label:'Time',kind:'time'}]);
is('a bad time is refused', gr.set(0,4,'99:99'), false);
is('...leaving the cell alone', gr.rows[0].time, '');
is('a loose time is accepted', gr.set(0,4,'6'), true);
is('...and normalised', gr.rows[0].time, '06:00');

console.log(fail ? '\n  ' + fail + ' FAILING' : '\n  all pass');
process.exit(fail ? 1 : 0);
