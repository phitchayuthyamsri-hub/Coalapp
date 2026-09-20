// The Location table agrees with itself: header, rows and structure.
//
//   node tests/test_anchor_columns.js
//
// Added 20/09/2026, when the conditions became columns, and rewritten when the
// list became a real <table>. A row carrying more cells than the header does
// not fail loudly - the header just drifts one column away from the values
// underneath it. That is the sort of thing an eye forgives in a screenshot, so
// it is checked here instead.
const fs = require('fs'), path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'app', 'tool', 'index.html'), 'utf8');

let FAIL = 0;
function check(label, got, want) {
  const ok = got === want;
  if (!ok) FAIL++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(52) +
              (ok ? '' : `got ${got} want ${want}`));
}

// The header is cleared first (head.innerHTML = ''), so match the assignment
// that actually builds it, not the reset just above.
const head = html.match(/head\.innerHTML =\s*('<tr><th rowspan[\s\S]*?);\n/);
const body = html.match(/li\.innerHTML = `([\s\S]*?)`;\n/);
if (!head || !body) { console.log('  FAIL  could not find the header or the row'); process.exit(1); }
// Two header rows: the ones that span both, plus the two under Window time.
// What must match the body is the number of LEAF columns.
const spanning = (head[1].match(/<th rowspan="2"/g) || []).length;
const sub = (head[1].match(/<th class="sub">/g) || []).length;
const headCols = spanning + sub;
const bodyCols = (body[1].match(/<td[ >]/g) || []).length;

console.log('the Location table agrees with itself');
check('leaf columns in the header', headCols, 11);
check('row cells match the header', bodyCols, headCols);
check('Window time groups two of them',
      /<th colspan="2" class="grouped">Window time<\/th>/.test(head[1]), true);
check('No# is the first column', /<tr><th rowspan="2">No#<\/th>/.test(head[1]), true);
check('the row number is the first cell', /^\s*<td class="rowno">/m.test(body[1]), true);

console.log('\nit is a table, and it fits its content');
check('the list is a <table>', /<table class="anchor-list" id="anchorList">/.test(html), true);
check('rows are <tr>', /createElement\('tr'\)/.test(html), true);
check('width is auto, not stretched', /\.anchor-list \{[\s\S]{0,200}?width: auto;/.test(html), true);
check('cells do not wrap', /\.anchor-list th, \.anchor-list td \{[\s\S]{0,300}?white-space: nowrap;/.test(html), true);
check('the reorder arrows are gone', /anchor-move|moveAnchor|data-act="up"/.test(html), false);

// A window belongs to a direction (user, 20/09): one cell for the run to the
// port, one for the run back. Each holds its own open and close, on one line -
// they wrapped onto two while this was a fixed-width grid column.
const winCells = body[1].match(/<td class="cell-window">[\s\S]*?<\/td>/g) || [];
check('a window cell per direction', winCells.length, 2);
winCells.forEach((cell, i) =>
  check(`...cell ${i + 1} holds an open and a close`,
        (cell.match(/type="time"/g) || []).length, 2));
check('the two directions are different fields',
      /c-out-open/.test(body[1]) && /c-back-open/.test(body[1]), true);

console.log('\nevery condition cell has a handler');
['c-type', 'c-out-open', 'c-out-close', 'c-back-open', 'c-back-close',
 'c-bays', 'c-load'].forEach(act => {
  const inMarkup = html.includes(`data-act="${act}"`);
  const inHandler = new RegExp(`'${act}':`).test(html);
  check(act, inMarkup && inHandler, true);
});

console.log('\nthe map is its own page');
check('the map page exists', /data-page-panel="locmap"/.test(html), true);
check('there is still exactly one map element',
      (html.match(/<div id="map"><\/div>/g) || []).length, 1);
// Compare against the PAGE divs, not any mention of the name: the stylesheet
// carries [data-page-panel="anchors"] selectors long before the markup does.
check('the map div sits inside the map page',
      html.indexOf('<div id="map">') > html.indexOf('<div class="page" data-page-panel="locmap">') &&
      html.indexOf('<div id="map">') < html.indexOf('<div class="page" data-page-panel="anchors">'), true);
check('editing a shape goes to the map',
      /function startEditingAnchor\(id\) \{\s*\n\s*goToLocMap\(id\);/.test(html), true);
check('the gear and its panel are gone', /condBox|data-act="cond"/.test(html), false);

console.log('\n  ' + (FAIL ? FAIL + ' FAILED' : 'all pass'));
process.exit(FAIL ? 1 : 0);
