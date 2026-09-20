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
check('the API sends the path and its type',
      sent.includes('sequence') && sent.includes('kind'), true);
check('...and not two legs on one route',
      sent.includes('fronthaul') || sent.includes('backhaul'), false);
sent.forEach(f => check(`the page knows about "${f}"`, html.includes(f), true));
check('the page never reads a leg that no longer exists',
      /\br\.fronthaul\b|\br\.backhaul\b/.test(html), false);

// Each direction is its own route (user, 20/09), so the type is a column in
// the row, and the three kinds must match the server's list exactly.
console.log('\nthe type');
const kinds = (api.match(/ROUTE_KINDS = \(([^)]*)\)/) || ['', ''])[1]
  .split(',').map(x => x.trim().replace(/['"]/g, '')).filter(Boolean).sort();
check('the server offers three kinds', kinds.join(','), 'any,backhaul,fronthaul');
kinds.forEach(k => check(`the page offers "${k}"`,
                         new RegExp("'" + k + "'").test(html), true));
check('the type is a dropdown in the row', /data-act="r-kind"/.test(html), true);
check('a bad type is refused, not corrected',
      /a route is a fronthaul, a backhaul, or any/.test(api), true);

console.log('\nthe table');
const head = html.match(/head\.innerHTML = ('<tr><th>No#<\/th><th>Name<\/th>[\s\S]*?);\n/);
// There are two tables on this page now, so pick the row by what is in it
// rather than by which one comes first.
const rows = [...html.matchAll(/tr\.innerHTML = `([\s\S]*?)`;\n/g)].map(m => m[1]);
// Shaped like a match result so the checks below read the same: [1] is the row.
const body = [null, rows.find(r => r.includes('cell-kind'))];
if (!head || !body[1]) { console.log('  FAIL  could not find the route header or row'); process.exit(1); }
check('header cells', (head[1].match(/<th>/g) || []).length, 7);
check('row cells match the header', (body[1].match(/<td[ >]/g) || []).length, 7);
check('it is the same table as Locations',
      /<table class="grid-table route-list" id="routeList">/.test(html), true);
check('the type sits beside the stops',
      /<th>Type<\/th><th>Stops, in order<\/th>/.test(head[1]), true);

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

// A backhaul is not declared per truck (user, 20/09): which way a truck comes
// home varies by trip, and the engine already works it out from where it went.
// So the declaration list must not offer one for the truck's single slot -
// otherwise a truck can be declared as running its cycle backwards.
console.log('\nthe backhaul is not declared per truck');
const sub = fs.readFileSync(path.join(root, 'app', 'templates', 'subcontractor.html'), 'utf8');
check('the declaration list drops backhaul routes from the picker',
      /ROUTES\.filter\(r => \(r\.kind \|\| 'any'\) !== 'backhaul'\)/.test(sub), true);
check('...and the column says it is the way out', /label:'Route out'/.test(sub), true);
check('a backhaul route says why its Trucks cell is empty',
      /kind === 'backhaul' \?[\s\S]{0,120}?not declared/.test(html), true);

// Fit-to-content, which this page keeps having to be told: a picker holding a
// handful of Location names should not stretch the width of the window.
check('the add-a-Location picker fits its content',
      /\.leg-add select \{[\s\S]{0,60}?flex: 0 0 auto; width: auto;/.test(html), true);

// The planning figures moved here whole (user, 20/09). They sat on
// Operations > Planner while the routes they describe sat here, so the same
// corridor was described in two places. The STORE never moved - planner.py
// still reads PlanSetting and RouteLeg - only the screen did.
console.log('\nthe planning figures');
check('the legs get their own section, KM and time travel',
      /<h2>KM &amp; time travel/.test(html), true);
check('...with its own table', /<table class="grid-table" id="legTable">/.test(html), true);
check('what is left keeps the figures table',
      /<table class="grid-table" id="figureList">/.test(html), true);
check('read from the planner own endpoint',
      /fetch\('\/api\/shift\/settings'\)/.test(html), true);
check('...and written back to the same one',
      /fetch\('\/api\/shift\/settings', \{[\s\S]{0,80}?method: 'POST'/.test(html), true);
check('who may edit is the server answer, not a guess',
      /STATE\.figuresCanEdit = !!j\.can_edit/.test(html), true);
check('a leg distance is editable here', /legkm:/.test(html), true);
check('the driving time is shown, not worked out by eye',
      /function figHours\(km, speed\)/.test(html), true);

// A place answers for its own figures now (user, 20/09). The planner asks the
// Location first and falls back to the stored figure only while that Location
// is blank - so those figures are shown here, not edited here.
console.log('\nthe places answer for themselves');
const plannerPy = fs.readFileSync(path.join(root, 'app', 'planner.py'), 'utf8');
const shiftPy = fs.readFileSync(path.join(root, 'app', 'shift_routes.py'), 'utf8');
check('the planner reads Locations by role', /def _by_role\(\):/.test(plannerPy), true);
check('...and falls back to the figure when one is blank',
      /return \(\(w\[0\], w\[1\]\), \(w\[2\], w\[3\]\)\) if w else \(hhmm\(ko, do\), hhmm\(kc, dc\)\)/.test(plannerPy), true);
check('the list of which figures moved lives in one place',
      /LOCATION_DERIVED = \{/.test(plannerPy), true);
check('...and the API hands it to the page',
      /"from_location": LOCATION_DERIVED\.get\(p\.key\)/.test(shiftPy), true);
check('the moved figures are off the screen entirely',
      /Answered by Setting . Location/.test(html), false);
check('...and the three that are left stay editable',
      /own\.forEach\(f => \{[\s\S]{0,400}?figInput\(f\.key/.test(html), true);
check('border clearance is one of them, having nowhere else to live',
      /"clear_h": hours\("clearance_hours", 3\.0\)/.test(plannerPy), true);
check('...so it is not claimed by a Location',
      /"clearance_hours":/.test(plannerPy), false);
['border_open', 'ql49_in_open', 'port_open', 'mine_bays', 'load_hours', 'unload_hours',
 'port_bays', 'mine_247'].forEach(k =>
  check(`"${k}" comes from a Location`, new RegExp('"' + k + '":').test(plannerPy), true));
check('rest before turning again stays a figure',
      /"turn_gap_h": hours\("turn_gap_hours", 0\.0\)/.test(plannerPy), true);
check('...as does which way home', /"cutoff": hhmm\("backhaul_cutoff", "14:00"\)/.test(plannerPy), true);

const shiftApi = fs.readFileSync(path.join(root, 'app', 'shift_routes.py'), 'utf8');
check('the endpoint takes a distance now',
      /key\.startswith\("legkm:"\)/.test(shiftApi), true);
check('a blank distance clears it rather than reading as zero',
      /if val == "":[\s\S]{0,200}?r\.road_km = None/.test(shiftApi), true);
check('changing figures stays a planner-or-admin job',
      /Only a planner or an admin may change planning figures/.test(shiftApi), true);

const planner = fs.readFileSync(path.join(root, 'app', 'templates', 'dispatch_planner.html'), 'utf8');
check('the planner page no longer edits them',
      /<div id="settings"><\/div>/.test(planner), false);
check('...and says where they went',
      /moved to <b>Setting &rarr; Route<\/b>/.test(planner), true);
check('the page can scroll, now that it holds two panels',
      /\[data-page-panel="route"\] \.page-pad \{ overflow-y: auto; \}/.test(html), true);
check('its map survived the move',
      /data-tab="figures">Corridor map</.test(planner), true);

console.log('\n  ' + (FAIL ? FAIL + ' FAILED' : 'all pass'));
process.exit(FAIL ? 1 : 0);
