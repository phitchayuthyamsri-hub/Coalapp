// The declaration upload names its delivery date, and files the sheet the day before.
//
// An upload once went to whatever day the page's own picker happened to show, and
// a new day's file replaced the previous day's sheet. These checks pin the date
// arithmetic the fix relies on, and that the upload no longer reads that picker.
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync('app/templates/subcontractor.html', 'utf8');

let fail = 0;
function is(label, got, want){
  const ok = got === want;
  if (!ok) fail++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(52)
    + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}

// Only the helper block, so nothing that boots the page has to run here.
const start = html.indexOf('// ── delivery date for an upload');
const end = html.indexOf("$('#pick').onclick", start);
is('the delivery-date helpers exist', start >= 0 && end > start, true);

const sandbox = {console, Date};
vm.createContext(sandbox);
try {
  vm.runInContext(html.slice(start, end), sandbox);
  const run = js => vm.runInContext(js, sandbox);
  is('delivery 16 Sep is the sheet sent 15 Sep', run("sheetDateFor('2026-09-16')"), '2026-09-15');
  is('...across a month end', run("sheetDateFor('2026-10-01')"), '2026-09-30');
  is('...across a year end', run("sheetDateFor('2027-01-01')"), '2026-12-31');
  is('...across a leap day', run("sheetDateFor('2028-03-01')"), '2028-02-29');
  is('dates read day first, with the weekday', run("dayLabel('2026-09-16')"), 'Wed 16-09-26');
  is('shifting forward works too', run("isoShift('2026-09-30', 2)"), '2026-10-02');
} catch (e) {
  console.log('  HELPERS THREW: ' + e.message);
  fail++;
}

is('the upload files under the sheet date', html.indexOf("fd.append('date', sheet);") >= 0, true);
is('...and no longer reads the top picker', html.indexOf("fd.append('date', $('#day').value)") < 0, true);
is('the delivery picker has no silent default',
   /<option value="">— choose the delivery date —<\/option>/.test(html), true);
is('an upload with no delivery date is refused', html.indexOf('Pick the delivery date first') >= 0, true);
is('a confirmed sheet is called locked, not replaced',
   html.indexOf('cannot be replaced by an upload') >= 0, true);
is('...and an upload onto it stops before any dialog',
   /if \(ex && ex.state === 'confirmed'\)\{[\s\S]{0,400}?return;[\s\S]{0,120}?confirm\(/
     .test(html), true);

console.log(fail ? '\n  ' + fail + ' FAILING' : '\n  all pass');
process.exit(fail ? 1 : 0);
