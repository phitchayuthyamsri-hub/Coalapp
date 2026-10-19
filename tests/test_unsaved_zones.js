// "Leave site?" only when there really is a zone to lose (19/10/2026).
//
// The tool page asked before every close or refresh, whatever page it was on.
// It counts a zone with a browser id (anc_...) as drawn-but-not-applied, and
// the first six zones still sit in the store under their old browser ids
// (anc_default_0..5) beside the server's copies of the same places - so the
// count was never zero. Apply would also have sent those six to the server as
// new, duplicate zones.
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync('app/tool/index.html', 'utf8').replace(/\r\n/g, '\n');
const grab = (re, what) => { const m = html.match(re); if (!m) throw new Error('not found: ' + what); return m[0]; };
const src = [
  grab(/function isLegacyTwin\(a\) \{[\s\S]*?\n\}/, 'isLegacyTwin'),
  grab(/function isUnsavedZone\(a\) \{[\s\S]*?\n\}/, 'isUnsavedZone'),
  grab(/function unsavedZoneCount\(\) \{[\s\S]*?\n\}/, 'unsavedZoneCount'),
].join('\n');

const NAMES = ['QL49', 'Chan May port', 'XPPL Mine', 'XPPL Loading area', 'Lalay border', 'Detour route'];
const sandbox = {STATE: {
  anchors: [...NAMES, 'A Ngo Warehouse'].map((name, i) => ({id: String(i + 1), name}))
    .concat(NAMES.map((name, i) => ({id: 'anc_default_' + i, name}))),
  retiredAnchorIds: [], condDirty: false}};
vm.createContext(sandbox);
vm.runInContext(src, sandbox);
const run = js => vm.runInContext(js, sandbox);

let fail = 0;
function is(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want); if (!ok) fail++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(58)
    + (ok ? '' : 'got ' + JSON.stringify(got) + ' want ' + JSON.stringify(want)));
}

console.log('the store as it is on prod');
is('nothing to lose: no "Leave site?"', run('unsavedZoneCount()'), 0);
is('an old copy of a server zone is not unsaved', run("isUnsavedZone({id:'anc_default_0', name:'QL49'})"), false);

console.log('\nreal unsaved work still counts');
run("STATE.anchors.push({id:'anc_1791962715000_42', name:'New yard'})");
is('a zone just drawn here', run('unsavedZoneCount()'), 1);
run("STATE.anchors.push({id:'anc_default_9', name:'Never applied'})");
is('an old browser zone the server never got', run('unsavedZoneCount()'), 2);
run("STATE.condDirty = true");
is('a changed condition', run('unsavedZoneCount()'), 3);

console.log('\nApply leaves the old copies alone');
is('the push loop skips them', /if \(isLegacyTwin\(a\)\) continue;/.test(html), true);

console.log(fail ? '\n  ' + fail + ' FAILING' : '\n  all pass');
process.exit(fail ? 1 : 0);
