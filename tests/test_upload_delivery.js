// A sheet is dated by the day its trucks are USED, and an upload names that day.
//
// An upload once went to whatever day the page's own picker happened to show, and
// a new day's file replaced another day's sheet. Then the picker, the upload and
// the rows all meant different days. These checks pin the one-date rule.
const fs = require('fs'), vm = require('vm');
const read = p => fs.readFileSync(p, 'utf8');
const html = read('app/templates/subcontractor.html');

let fail = 0;
function is(label, got, want){
  const ok = got === want;
  if (!ok) fail++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(56)
    + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}

// Only the helper block, so nothing that boots the page has to run here.
const start = html.indexOf('// ── the date an upload is for');
const end = html.indexOf("$('#pick').onclick", start);
is('the upload-date helpers exist', start >= 0 && end > start, true);

const sandbox = {console, Date};
vm.createContext(sandbox);
try {
  vm.runInContext(html.slice(start, end), sandbox);
  const run = js => vm.runInContext(js, sandbox);
  is('dates read day first, with the weekday', run("dayLabel('2026-09-16')"), 'Wed 16/09/2026');
  is('shifting a day crosses a month end', run("isoShift('2026-09-30', 1)"), '2026-10-01');
  is('...and a year end', run("isoShift('2026-12-31', 1)"), '2027-01-01');
} catch (e) {
  console.log('  HELPERS THREW: ' + e.message);
  fail++;
}

is('the upload files under the date picked, unchanged', html.indexOf('const sheet = delivery;') >= 0, true);
is('...sent as that date', html.indexOf("fd.append('date', sheet);") >= 0, true);
is('no day-before arithmetic is left', html.indexOf('sheetDateFor') < 0, true);
is('the upload no longer reads the top picker', html.indexOf("fd.append('date', $('#day').value)") < 0, true);
is('the picker has no silent default',
   /<option value="">— choose the day these trucks are used —<\/option>/.test(html), true);
is('an upload with no date is refused', html.indexOf('Pick the date first') >= 0, true);
is('a confirmed sheet is called locked, not replaced',
   html.indexOf('cannot be replaced by an upload') >= 0, true);
is('...and an upload onto it stops before any dialog',
   /if \(ex && ex.state === 'confirmed'\)\{[\s\S]{0,400}?return;[\s\S]{0,120}?confirm\(/.test(html), true);

// One date, meaning one thing, on every page that picks a sheet.
for (const page of ['subcontractor', 'shift_board', 'approvals']) {
  const t = read('app/templates/' + page + '.html');
  is(page + ': the date is the day trucks are used',
     t.indexOf('Date &mdash; the day these trucks are used') >= 0, true);
  is(page + ': no "day the sheet was sent" wording',
     /day (you send this|the sheet was) sent|day you send this sheet/.test(t), false);
}

console.log(fail ? '\n  ' + fail + ' FAILING' : '\n  all pass');
process.exit(fail ? 1 : 0);
