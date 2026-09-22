// The declared table as a picture (22/09/2026).
//
// Run: node tests/test_capture.js
//
// The drawing needs a canvas, which node has not got; what can be checked is
// the layout it draws from, the file name it gives, and that both pages carry
// the button and the script.
const fs = require('fs'), vm = require('vm'), path = require('path');
const root = path.join(__dirname, '..');
const src = fs.readFileSync(path.join(root, 'app/static/capture.js'), 'utf8');
const sandbox = { window: {}, navigator: {}, document: {} };
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(src, sandbox);
const TC = sandbox.TableCapture;

let fail = 0;
function is(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) fail++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(56)
    + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}

// 7px a character, 8 when bold: enough to see the widths come from content.
const measure = (s, bold) => s.length * (bold ? 8 : 7);
const cols = [{label: 'Truck'}, {label: 'Remark'}];
const lay = TC.layout(cols, [['20H01498', 'border queue'], ['20C10615', '']], measure);
is('a column is as wide as its widest value, plus padding', lay.widths[0], 8 * 7 + 20);
is('...or its heading when that is wider', lay.widths[1], Math.max(6 * 8, 12 * 7) + 20);
is('the picture is the columns plus a margin each side', lay.width, lay.widths[0] + lay.widths[1] + 48);
const wide = TC.layout(cols, [['x', 'a'.repeat(200)]], measure);
is('a long remark is capped, not a metre wide', wide.widths[1], 320);
is('height grows with the rows',
   TC.layout(cols, [[1, 2], [3, 4], [5, 6]], measure).height - lay.height, 26);

is('the file name is safe for any system', TC.safeName('Bac Nam_2026-09-23_declared'), 'Bac_Nam_2026-09-23_declared');
is('...and never empty', TC.safeName('///'), 'table');
is('the stamp reads day first', /^\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}$/.test(TC.stamp()), true);

console.log('\nboth pages carry it');
for (const f of ['subcontractor.html', 'shift_board.html']){
  const html = fs.readFileSync(path.join(root, 'app/templates', f), 'utf8');
  is(f + ' loads the script', /static\/capture\.js\?v=/.test(html), true);
  is(f + ' has the button', /&#128247; Capture<\/button>/.test(html), true);
  is(f + ' names the file by company and day', /_declared'/.test(html), true);
  is(f + ' says whether the picture was copied', /ready to paste/.test(html), true);
}

console.log(fail ? '\n  ' + fail + ' FAILING' : '\n  all pass');
process.exit(fail ? 1 : 0);
