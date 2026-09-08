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

console.log(fail ? '\n  ' + fail + ' FAILING' : '\n  all pass');
process.exit(fail ? 1 : 0);
