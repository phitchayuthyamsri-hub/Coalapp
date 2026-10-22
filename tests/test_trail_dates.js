// The truck trail says WHEN, not only what time (22/10/2026).
//
// 20H00716's trail read "last seen 12:08" on 22/10 - it was 12:08 on 21/10,
// and the tracker had been silent since (the truck had moved to Viettel while
// the Fleet page still said TCT). The tiles now carry the day, and a trail
// whose last point is hours old says so.
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync('app/templates/truck_trail.html', 'utf8').replace(/\r\n/g, '\n');
const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(html.match(/function dmhm\(s\)[^\n]*/)[0], sandbox);

let fail = 0;
function is(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want); if (!ok) fail++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(58)
    + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}
is('a time carries its day', vm.runInContext("dmhm('2026-10-21 12:08:45')", sandbox), '21/10 12:08');
is('first and last seen use it',
   /first seen<b>' \+ \(pts\.length \? dmhm\(/.test(html) && /last seen<b>' \+ \(pts\.length \? dmhm\(/.test(html), true);
is('a quiet tracker is named', /No GPS position since <b>/.test(html), true);
console.log(fail ? '\n  ' + fail + ' FAILING' : '\n  all pass');
process.exit(fail ? 1 : 0);
