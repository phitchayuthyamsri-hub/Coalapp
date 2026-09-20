// The Location list is a table: its header, its rows and its CSS grid must
// agree on how many columns there are.
//
//   node tests/test_anchor_columns.js
//
// Added 20/09/2026, when the conditions became columns. A grid whose rows
// carry more cells than the template declares does not fail loudly - the
// extras wrap onto an invisible second line, or the header drifts one column
// away from the values underneath it. That is exactly the sort of thing a
// screenshot is checked for and a person's eye forgives, so it is checked
// here instead.
const fs = require('fs'), path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'app', 'tool', 'index.html'), 'utf8');

let FAIL = 0;
function check(label, got, want) {
  const ok = got === want;
  if (!ok) FAIL++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(52) +
              (ok ? '' : `got ${got} want ${want}`));
}

// 1. the CSS grid
const grid = html.match(/\.anchor-list li, \.anchor-list-head \{[\s\S]*?grid-template-columns:([\s\S]*?);/);
if (!grid) { console.log('  FAIL  could not find the grid template'); process.exit(1); }
const cssCols = grid[1].trim().split(/\s+(?![^(]*\))/).filter(Boolean).length;

// 2. the header row
const head = html.match(/headRow\.innerHTML = ([\s\S]*?);\n/);
const headCols = (head[1].match(/<span>/g) || []).length;

// 3. the body row: top-level elements of the template literal
const body = html.match(/li\.innerHTML = `([\s\S]*?)`;\n/);
// A cell is a top-level element OR an interpolated one (${overrideMark} is a
// button built just above); both occupy a grid column just the same.
const CELL = new RegExp("^      (<(span|label|button)\\b|\\${\\w+})", "gm");
const bodyCols = (body[1].match(CELL) || []).length;

console.log('the Location list agrees with itself');
check('css grid columns', cssCols, 10);
check('header cells match the grid', headCols, cssCols);
check('row cells match the grid', bodyCols, cssCols);

// 4. every condition cell is actually wired to a handler
console.log('\nevery condition cell has a handler');
['c-type', 'c-open', 'c-close', 'c-bays', 'c-load'].forEach(act => {
  const inMarkup = html.includes(`data-act="${act}"`);
  const inHandler = new RegExp(`'${act}':`).test(html);
  check(act, inMarkup && inHandler, true);
});

// 5. the map moved out, and everything that needs it goes to its page
console.log('\nthe map is its own page');
check('the map page exists', /data-page-panel="locmap"/.test(html), true);
check('there is still exactly one map element',
      (html.match(/<div id="map"><\/div>/g) || []).length, 1);
check('the map div sits inside the map page',
      html.indexOf('<div id="map">') > html.indexOf('data-page-panel="locmap"') &&
      html.indexOf('<div id="map">') < html.indexOf('data-page-panel="anchors"'), true);
check('editing a shape goes to the map', /function startEditingAnchor\(id\) \{\s*\n\s*goToLocMap\(id\);/.test(html), true);
check('the gear and its panel are gone', /condBox|data-act="cond"/.test(html), false);

console.log('\n  ' + (FAIL ? FAIL + ' FAILED' : 'all pass'));
process.exit(FAIL ? 1 : 0);
