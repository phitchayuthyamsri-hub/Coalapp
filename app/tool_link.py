# -*- coding: utf-8 -*-
"""Feed the legacy tool from the database instead of from dropped files.

The tool at /tool is a self-contained browser application: five drop-zones, and
everything it parses kept in that browser's own localStorage and IndexedDB. It
has never read the database, which is why its Timeline showed seventeen trucks
from a file dropped months ago while the fleet had grown to fifty-eight, and why
its Dispatch Plan was empty on a day the planner had issued one.

So this seeds the same stores the drop-handlers write, from the same tables the
rest of the system uses:

    fleet   <- truck                    (actualGpsFleet_v2)
    plan    <- the issued PlanSnapshot  (actualGpsDataInput_v1 .plan)
    status  <- the readiness rows       (actualGpsDataInput_v1 .status)
    pings   <- gps_ping                 (IndexedDB 'actual_gps')

The weighbridge is deliberately NOT seeded. It is the one input that comes from
outside this system, which is the whole of its value: it is the independent
check on everything above. Feeding it from our own records would leave it
agreeing with us by construction.

Seeding is synchronous for the three small stores - a classic <script> tag
blocks parsing, so the tool's own loaders find the data already there - and
asynchronous for pings, because IndexedDB has no synchronous API.
"""
import json
from datetime import datetime, timedelta

from flask import Blueprint, Response, request
from flask_login import current_user, login_required

from . import engine
from .models import (DailyList, DailyListRow, FleetCommitment, GpsPing,
                     PlanSnapshot, Truck, db)

bp = Blueprint("tool_link", __name__)

# The tool keys its stores by these exact names.
FLEET_KEY = "actualGpsFleet_v2"
DIN_KEY = "actualGpsDataInput_v1"
IDB_NAME, IDB_VERSION = "actual_gps", 1
SEED_FILE_ID = "server:coalapp"        # so seeded pings are distinguishable


def _role():
    return (getattr(current_user, "role", "") or "").lower()


def _own_plates():
    """A subcontractor sees their own trucks and nobody else's.

    Same rule the rest of the system applies. Returns None for "everything".
    """
    if _role() != "subcontractor":
        return None
    sub_id = getattr(current_user, "subcontractor_id", None)
    if not sub_id:
        return set()
    plates = {c.key for c in FleetCommitment.query.filter_by(
        subcontractor_id=sub_id, released_on=None).all()}
    rows = (db.session.query(DailyListRow.key)
            .join(DailyList, DailyList.id == DailyListRow.list_id)
            .filter(DailyList.subcontractor_id == sub_id).all())
    return plates | {r[0] for r in rows}


def _fleet(only):
    out = {}
    for t in Truck.query.order_by(Truck.plate).all():
        key = engine.norm_plate(t.plate)
        if only is not None and key not in only:
            continue
        out[t.plate] = {
            "status": (t.status or "online"),
            "added": int((t.added or datetime.utcnow()).timestamp() * 1000),
            "phone": t.phone or "",
            "gps": t.gps_provider or "",
            "effFrom": t.eff_from or "",
            "effTo": t.eff_to or "",
        }
    return out


def _plan(only):
    """The issued plan, in the shape the Dispatch Plan drop-handler produces.

    The snapshot has no separate time for the border on the way back - the model
    times the two ends of the return leg and not its middle - so borderBack is
    left null rather than invented. The tool already treats a missing time as
    unknown.
    """
    out = {}
    for snap in PlanSnapshot.query.order_by(PlanSnapshot.id.asc()).all():
        for r in (snap.rows or []):
            plate = r.get("plate") or ""
            key = engine.norm_plate(plate)
            if only is not None and key not in only:
                continue
            t = r.get("t") or {}
            day = r.get("day") or (t.get("arrive_mine") or "")[:10]
            if not plate or not day:
                continue
            out["%s|%s" % (key, day)] = {
                "plate": key, "date": day,
                "loadStart": t.get("load_start"),
                "mineArrive": t.get("arrive_mine"),
                "depMine": t.get("load_end"),
                "borderArrive": t.get("arrive_border"),
                "depBorder": t.get("cross_border"),
                "portArrive": t.get("arrive_port"),
                "depPort": t.get("depart_port"),
                "borderBack": None,
                "mineReturn": t.get("back"),
            }
    return out


def _status(only):
    """What each company declared, per truck per day - the Truck Status grid.

    The note is the declaration in the company's own words: the leg when it is
    working, the reason when it is not. That is exactly what the dropped Truck
    Status file carried.
    """
    cell, disp, plates, dates = {}, {}, [], set()
    q = (db.session.query(DailyListRow, DailyList)
         .join(DailyList, DailyList.id == DailyListRow.list_id)
         .order_by(DailyListRow.plate))
    for row, dl in q.all():
        key = engine.norm_plate(row.plate or "")
        if not key or (only is not None and key not in only):
            continue
        day = row.arrive_date or dl.list_date
        if not day:
            continue
        note = (row.note or row.reason or "").strip()
        if not note:
            note = "ready" if row.ready else "not running"
        if key not in cell:
            cell[key] = {}
            disp[key] = row.plate
            plates.append(key)
        cell[key][day] = note
        dates.add(day)
    if not plates:
        return None
    return {"plates": plates, "disp": disp, "dates": sorted(dates), "cell": cell}


@bp.get("/api/tool/pings")
@login_required
def tool_pings():
    """GPS positions, in the record shape the IndexedDB store holds."""
    only = _own_plates()
    days = request.args.get("days", type=int) or 400   # the whole history; it is only a few thousand rows
    since = datetime.utcnow() + timedelta(hours=7) - timedelta(days=days)
    rows = (GpsPing.query.filter(GpsPing.dt >= since)
            .order_by(GpsPing.plate, GpsPing.dt).all())
    out = []
    for p in rows:
        key = engine.norm_plate(p.plate)
        if only is not None and key not in only:
            continue
        out.append({"plate": key, "t": int(p.dt.timestamp() * 1000),
                    "lat": p.lat, "lng": p.lng,
                    "status": p.status or "", "speed": p.speed or 0.0})
    return Response(json.dumps({"pings": out, "count": len(out),
                                "fileId": SEED_FILE_ID}),
                    mimetype="application/json",
                    headers={"Cache-Control": "no-store"})


@bp.get("/api/tool/seed.js")
@login_required
def tool_seed_js():
    only = _own_plates()
    seed = {"fleet": _fleet(only), "plan": _plan(only), "status": _status(only),
            "at": datetime.utcnow().isoformat(timespec="seconds")}
    js = SEED_JS.replace("__SEED__", json.dumps(seed)) \
                .replace("__FLEET_KEY__", json.dumps(FLEET_KEY)) \
                .replace("__DIN_KEY__", json.dumps(DIN_KEY)) \
                .replace("__IDB_NAME__", json.dumps(IDB_NAME)) \
                .replace("__IDB_VERSION__", str(IDB_VERSION)) \
                .replace("__FILE_ID__", json.dumps(SEED_FILE_ID))
    return Response(js, mimetype="application/javascript",
                    headers={"Cache-Control": "no-store"})


SEED_JS = r"""
(function () {
  var SEED = __SEED__;
  var FLEET_KEY = __FLEET_KEY__, DIN_KEY = __DIN_KEY__;
  var IDB_NAME = __IDB_NAME__, IDB_VERSION = __IDB_VERSION__;
  var FILE_ID = __FILE_ID__;

  // ---- the three small stores, written before the app reads them ----------
  try {
    localStorage.setItem(FLEET_KEY, JSON.stringify(SEED.fleet || {}));
    var din = {};
    try { din = JSON.parse(localStorage.getItem(DIN_KEY)) || {}; } catch (e) {}
    // Replace only what the server is the authority for. The operator's own
    // manual overrides, assignments and weighbridge fills are theirs.
    din.plan = SEED.plan || {};
    if (SEED.status) din.status = SEED.status;
    localStorage.setItem(DIN_KEY, JSON.stringify(din));
    window.__TOOL_SEEDED_AT = SEED.at;
  } catch (e) { console.warn('[tool-link] store seed failed', e); }

  // ---- pings: IndexedDB has no synchronous API, so this lands later -------
  function open() {
    return new Promise(function (res, rej) {
      var q = indexedDB.open(IDB_NAME, IDB_VERSION);
      q.onupgradeneeded = function (e) {
        var db = e.target.result;
        if (!db.objectStoreNames.contains('pings'))
          db.createObjectStore('pings', {keyPath: 'key'});
        if (!db.objectStoreNames.contains('datasets'))
          db.createObjectStore('datasets', {keyPath: 'id'});
      };
      q.onsuccess = function (e) { res(e.target.result); };
      q.onerror = function (e) { rej(e.target.error); };
    });
  }

  function syncPings() {
    var got;
    return fetch('/api/tool/pings', {credentials: 'same-origin'})
      .then(function (r) { return r.json(); })
      .then(function (j) { got = j; return open(); })
      .then(function (db) {
        return new Promise(function (res, rej) {
          var tx = db.transaction(['pings', 'datasets'], 'readwrite');
          var ps = tx.objectStore('pings');
          // Replace the previous server batch rather than piling copies up;
          // anything the operator dropped by hand keeps its own fileId.
          var cur = ps.openCursor(), added = 0;
          cur.onsuccess = function (e) {
            var c = e.target.result;
            if (c) {
              if (c.value && c.value.fileId === FILE_ID) c.delete();
              c.continue();
              return;
            }
            (got.pings || []).forEach(function (p) {
              ps.put({key: p.plate + '|' + p.t, fileId: FILE_ID, plate: p.plate,
                      t: p.t, lat: p.lat, lng: p.lng,
                      status: p.status, speed: p.speed});
              added++;
            });
            tx.objectStore('datasets').put({
              id: FILE_ID, name: 'Coalapp (live)', rows: added,
              added: Date.now(), from: '', to: ''});
          };
          tx.oncomplete = function () { res(added); };
          tx.onerror = function (e) { rej(e.target.error); };
        });
      });
  }

  function go() {
    syncPings().then(function (n) {
      console.log('[tool-link] ' + n + ' positions from the database');
      // Ask the tool to re-read its own store. If that hook is not there,
      // leave the page alone rather than reloading under the operator.
      if (typeof window.rebuildFromStore === 'function') {
        try { window.rebuildFromStore(); } catch (e) { console.warn(e); }
      }
    }).catch(function (e) { console.warn('[tool-link] ping sync failed', e); });
  }

  if (document.readyState === 'complete') setTimeout(go, 0);
  else window.addEventListener('load', function () { setTimeout(go, 0); });
})();
"""
