# coalapp — Project Context for Claude Code

## ⚠️ READ FIRST — SERVER ISOLATION (critical)

This project lives on a **dedicated, separate DigitalOcean droplet** that exists
ONLY for coalapp. It is NOT the main/primary server.

- Droplet IP: 157.230.240.226 (hostname: ubuntu-s-1vcpu-2gb-sgp1, Singapore)
- A DIFFERENT app called `logistics` runs at /var/www/logistics on gunicorn :5000.
  **That is a separate project. Do NOT touch it, read it, modify it, or reason about
  it.** coalapp and logistics are unrelated despite sharing the box.

**Past incident:** in a prior session, another AI assistant working on the *logistics*
project deleted the ENTIRE coalapp platform — `sudo rm` of /opt/coalapp, plus removing
its systemd service and nginx site. The SQLite database was lost permanently (no backup
existed). The app had to be rebuilt from GitHub and all data re-entered from scratch.

**Therefore, hard rules:**
- NEVER run destructive commands (`rm -rf`, service removal, nginx site deletion,
  DB drops) without explicit, specific human confirmation naming the exact path.
- Scope every action to `/opt/coalapp` only. Never operate on `/var/www/logistics`,
  port 5000, or anything outside coalapp.
- Assume there is STILL no database backup unless you verify one exists. Treat the
  live SQLite DB as irreplaceable.

## What coalapp is

A Flask + SQLite TMS (Transport Management System) for coal-haulage logistics. It
ingests GPS / Dispatch-Plan / Weighbridge / subcontractor-roster xlsx files, runs a
geofence visit-detection + cycle engine, and renders Performance / Daily-performance /
Timeline / Truck-status / Plan-vs-Actual dashboards for the Vietnam ops team.

Business context: coal trucks run Mine (XPPL, Laos) → Lalay border → QL49 → Chân Mây
port (Vietnam) and back, ~440 km, ~42 t/trip. A full cycle is ~68h actual vs a 48h
target. Fixed regulatory windows (border loaded crossing 15:00–19:00 once daily, QL49
inbound 19:00–24:00, port unload 07:00–17:00) make a full cycle physically impossible
in under ~24h — this constraint is load-bearing in the engine logic.

## Stack & layout

- Flask + Flask-SQLAlchemy + Flask-Login, SQLite, gunicorn (3 workers) on 127.0.0.1:8000
- nginx reverse-proxies :8080 → :8000 (port 80 is taken by the logistics app; do not use it)
- systemd unit: `coalapp.service` (User=www-data, WorkingDirectory=/opt/coalapp)
- Code: /opt/coalapp  |  Public GitHub: github.com/phitchayuthyamsri-hub/Coalapp
- Entry: wsgi.py → `create_app()` in app/__init__.py (calls db.create_all() on boot,
  so new models auto-create tables — no migration framework)
- config.py reads SECRET_KEY + DATABASE_URL from env (set in the systemd unit)

Repo root: wsgi.py, config.py, requirements.txt, deploy/ (coalapp.service,
nginx.conf.sample, setup.sh), README.md, and app/.

### app/ (the application)
- __init__.py   — app factory, db init, login manager, blueprint registration
- models.py     — User, Truck, GpsPing, Anchor, RouteLeg, KVStore, LoginEvent,
                  AreaTime, ActivityEvent, DispatchPlanRow, LoadActualRow, SubFleetRow
- api.py        — JSON endpoints: /api/kv (tool state sync), /api/event (activity),
                  /admin/activity + /admin/activity/export.xlsx
- auth.py       — register / login / logout
- views.py      — page routes; injects 3 scripts into the tool's <head> at serve time
                  (_BRIDGE = localStorage↔server sync, _GUARD = dwell tracking,
                  _EVENTS = action tracking)
- engine.py     — distance legs / ETA / cycle helpers (Python side)
- parsers.py    — server-side xlsx parsing (openpyxl)
- seed.py       — seeds default geofences (anchors) + route legs on first run
- activity.py   — activity/usage admin page logic
- tool/index.html — THE MAIN UI: ~10,900-line single-file app (HTML+CSS+JS). Almost
                  all dashboard logic lives here client-side. This is the heaviest file.
- templates/    — login, register, admin, activity, report, etc.
- static/       — bundled assets

## The big file: app/tool/index.html

This single file holds the entire client-side tool: geofence/visit/cycle engine, all
tabs, KPI math, filters, Leaflet map, xlsx parsing (SheetJS), WhatsApp dispatch, etc.
The Flask side mostly stores/serves; the analytics happen here in JS.

**Working rules for this file (learned the hard way):**
- It's huge — do NOT open it whole. Use `grep -n` / `sed -n` to locate and read spans.
- It has multiple `<script>` blocks. The main app logic is the block containing
  `function computePerf`. After ANY edit, extract that block and run `node --check`
  on it before considering the change done.
- Never put a literal `</script>` inside a JS string.
- Status flow: visits (buildVisits) → cycles (recomputeSequences / buildRouteCycles)
  → per-tab renders. The Performance/Daily KPIs come from `computePerf()`.

## Key engine concepts (so you don't re-derive or break them)

- **Weighbridge is authoritative** over GPS for load status. GPS is unreliable for
  confirming re-entry into the loading cycle.
- **24h re-arrival floor** (computePerf, marker `REARRIVE_FLOOR_MS`): a mine touch
  <24h after a truck's last *kept* arrival, with no border/port visit in between, is
  treated as linger / a mine-only-feed artifact and renders blank — it does NOT open a
  new scored event. A border/port visit in the gap overrides and keeps it. Rationale:
  a real full cycle can't complete in <24h, so closer touches can't be separate cycles.
- **Auto-deactivation** (`effExpired` / `effectiveStatus`): a truck whose "Effective To"
  date has passed (vs today) is treated as deactivated automatically; stored status is
  left intact so extending the date reactivates it.
- **Fleet scope filter** (`fleetScopeAllows`, scopes: all / in / out / deact): shared
  control across Timeline / Sequence / Route / Truck-status / visits table AND the Daily
  grid. `deact` shows only deactivated trucks and, on Timeline, ignores the date-range
  filter. Deactivated trucks are NO LONGER dropped at the data layer (their GPS is
  retained); they're filtered at render only. **Standing principle: do not delete/hide
  underlying data — filter at display, keep the data analyzable.**
- **Performance KPIs date-bounding:** cycle-based KPIs already exclude cycles after a
  truck's Effective To (via `inEff`). The weighbridge-based Trips/truck + Trucks-loading
  cards are monthly totals, bounded at month granularity only (`inEffMon`) — they cannot
  be split mid-month.
- **Plan date anchoring:** Dispatch-Plan computed columns carry bogus years; recover the
  real date from Load Start or Arrive Mine (whichever has a plausible 2020–2100 year).

## Deploy workflow (how changes reach the droplet)

The human deploys via GitHub web upload of the inner `app` folder, then on the droplet:

```
cd /opt/coalapp
sudo git checkout -- app/tool/index.html   # discard any direct-on-server edits first
sudo git pull
sudo chown -R www-data:www-data /opt/coalapp
sudo systemctl restart coalapp
```
Then hard-refresh the browser (Ctrl+Shift+R).

**Gotcha:** direct edits on the droplet put the server ahead of GitHub and cause pull
conflicts. Resolve with `git checkout -- <file>` before pulling. Prefer committing
through GitHub, not editing files live on the box.

## Open items / known gaps

- **No database backup exists.** Highest-priority operational risk. A nightly
  `sqlite3 .backup` to a path OUTSIDE /opt/coalapp (or a DO snapshot) is needed.
- `/register` is open on a public IP — should be locked down once accounts exist.
- Plain HTTP on :8080 (no TLS; would need a domain/cert).
- Manual "Deactivated" status WITHOUT an Effective To date isn't date-bounded anywhere.
- The mine-only-feed defect is upstream (GPS export dropping the route trail); the 24h
  floor is a display-side mitigation, not a root-cause fix.

## Verify the live build matches the latest code

```
cd /opt/coalapp
grep -c 'def track_event' app/api.py                # activity tracking
grep -c 'REARRIVE_FLOOR_MS' app/tool/index.html     # 24h floor
grep -c 'effectiveStatus' app/tool/index.html       # auto-deactivation
grep -c 'data-scope="deact"' app/tool/index.html    # deactivated filter
grep -c '_sc=pl=>fleetScopeAllows' app/tool/index.html  # daily scope filter
grep -c 'inEffMon' app/tool/index.html              # weighbridge month-bound
```
All non-zero = live code is current.
