// The Route page and the route API agree on what a route is called.
//
//   node tests/test_route_page.js
//
// Written on 20/09/2026 after exactly this went wrong. The API stopped
// sending `sequence` and started sending `fronthaul`/`backhaul`; the page was
// still reading `sequence`, threw while drawing, and rendered nothing. The
// screen said "No routes yet" while the database held two - so the routes
// looked impossible to create, and the real error was never shown.
//
// Nothing about that failed loudly. The server was fine, the tests were fine,
// and only the browser knew. So the field names are checked against each
// other here, from the two files that have to agree.
const fs = require('fs'), path = require('path');
const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'app', 'tool', 'index.html'), 'utf8');
const api = fs.readFileSync(path.join(root, 'app', 'api.py'), 'utf8');

let FAIL = 0;
function check(label, got, want) {
  const ok = got === want;
  if (!ok) FAIL++;
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label.padEnd(54) +
              (ok ? '' : `got ${got} want ${want}`));
}

// What the server actually puts in a route.
const routeApi = api.match(/def _route_api\([\s\S]*?\n\n/);
const sent = [...routeApi[0].matchAll(/"(\w+)":/g)].map(m => m[1]).sort();

console.log('the page reads what the API sends');
check('the API sends both legs',
      sent.includes('fronthaul') && sent.includes('backhaul'), true);
check('...and no longer a flat sequence', sent.includes('sequence'), false);
sent.forEach(f => check(`the page knows about "${f}"`, html.includes(f), true));
check('the page never reads r.sequence', /\br\.sequence\b/.test(html), false);

console.log('\nthe table');
const head = html.match(/head\.innerHTML = ('<tr><th>No#<\/th><th>Name<\/th>[\s\S]*?);\n/);
const body = html.match(/tr\.innerHTML = `([\s\S]*?)`;\n/);
if (!head || !body) { console.log('  FAIL  could not find the route header or row'); process.exit(1); }
check('header cells', (head[1].match(/<th>/g) || []).length, 7);
check('row cells match the header', (body[1].match(/<td[ >]/g) || []).length, 7);
check('it is the same table as Locations',
      /<table class="grid-table route-list" id="routeList">/.test(html), true);
check('both legs have a column',
      /Fronthaul — to port[\s\S]*?Backhaul — to mine/.test(head[1]), true);

console.log('\nthe old page is not a second editor');
check('the iframe is gone', /routeFrame|\/route\?embed=1/.test(html), false);
const shift = fs.readFileSync(path.join(root, 'app', 'shift_routes.py'), 'utf8');
check('/route sends you to the real one', /return redirect\("\/tool#route"\)/.test(shift), true);
check('its template is deleted',
      fs.existsSync(path.join(root, 'app', 'templates', 'route.html')), false);

// The gate that bit us this morning: the page must hide what the server
// would refuse, and both halves must name the same rule.
console.log('\nthe admin gate is in both halves');
check('the page has one', /MAY_EDIT_ROUTES = !!\(me\.is_admin \|\| me\.role === 'admin'\)/.test(html), true);
check('the server has the same one',
      /_may_edit_routes\(\)[\s\S]*?is_admin[\s\S]*?== "admin"/.test(api), true);
check('Save and New are hidden without it',
      /\['btnNewRoute', 'btnSaveRoutes'\][\s\S]{0,200}?MAY_EDIT_ROUTES \? '' : 'none'/.test(html), true);

console.log('\n  ' + (FAIL ? FAIL + ' FAILED' : 'all pass'));
process.exit(FAIL ? 1 : 0);
