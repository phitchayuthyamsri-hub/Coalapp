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
const head = html.match(/head\.innerHTML = ('<tr>[\s\S]*?);\n/);
const body = html.match(/li\.innerHTML = `([\s\S]*?)`;\n/);
if (!head || !body) { console.log('  FAIL  could not find the header or the row'); process.exit(1); }
const headCols = (head[1].match(/<th>/g) || []).length;
const bodyCols = (body[1].match(/<td[ >]/g) || []).length;

console.log('the Location table agrees with itself');
check('header cells', headCols, 10);
check('row cells match the header', bodyCols, headCols);
check('No# is the first column', /<tr><th>No#<\/th>/.test(head[1]), true);
check('the row number is the first cell', /^\s*<td class="rowno">/m.test(body[1]), true);

console.log('\nit is a table, and it fits its content');
check('the list is a <table>', /<table class="anchor-list" id="anchorList">/.test(html), true);
check('rows are <tr>', /createElement\('tr'\)/.test(html), true);
check('width is auto, not stretched', /\.anchor-list \{[\s\S]{0,200}?width: auto;/.test(html), true);
check('cells do not wrap', /\.anchor-list th, \.anchor-list td \{[\s\S]{0,300}?white-space: nowrap;/.test(html), true);
check('the reorder arrows are gone', /anchor-move|moveAnchor|data-act="up"/.test(html), false);

// The window is one cell holding both times: it wrapped onto two lines while
// it was a fixed-width grid column, which is what prompted the rewrite.
const winCell = (body[1].match(/<td class="cell-window">[\s\S]*?<\/td>/) || [''])[0];
check('the window is one cell', winCell !== '', true);
check('...holding both times', (winCell.match(/type="time"/g) || []).length, 2);

console.log('\nevery condition cell has a handler');
['c-type', 'c-open', 'c-close', 'c-bays', 'c-load'].forEach(act => {
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
