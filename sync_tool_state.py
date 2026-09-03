#!/usr/bin/env python3
"""
Feed the tool's shared store from the server's own data.

The tool pages (Fleet, Sequence, Timeline/Gantt) read two blobs out of the
shared store, which until now were only ever filled by uploading spreadsheets
by hand. Everything they need is already on the server: the fleet lives in the
truck table, and the positions arrive from the GPS providers every few hours.

    actualGpsFleet_v2   <- the truck table
    actualGpsTiming_v1  <- visits and cycles computed from gps_ping

So the Gantt now shows the trucks that are actually reporting, and it moves on
its own as the pullers run, instead of showing whatever was last uploaded.

Usage (on the server, from /opt/coalapp):
    python sync_tool_state.py

Run it after each GPS pull:
    cd /opt/coalapp && venv/bin/python gps_pull.py && venv/bin/python sync_tool_state.py

Idempotent: it rewrites both blobs from current data every time.
"""
import json
from datetime import datetime

from app import create_app
from app import engine
from app.models import db, Truck, GpsPing, Anchor, KVStore

FLEET_KEY = "actualGpsFleet_v2"
TIMING_KEY = "actualGpsTiming_v1"


def _ms(dt):
    """The tool works in epoch milliseconds; the engine works in datetimes."""
    return int(dt.timestamp() * 1000) if isinstance(dt, datetime) else None


def _kv_set(key, obj):
    row = db.session.get(KVStore, key)
    payload = json.dumps(obj, separators=(",", ":"))
    if row is None:
        db.session.add(KVStore(key=key, value=payload))
    else:
        row.value = payload
    return len(payload)


def build_fleet():
    """The tool keys its fleet on the plate; everything else hangs off that."""
    out = {}
    for t in Truck.query.order_by(Truck.plate).all():
        out[t.plate] = {
            "status": t.status or "online",
            "added": _ms(t.added) or 0,
            # Left as stored rather than filled with the placeholder number:
            # a blank here is honest, and the monitor board supplies its own
            # fallback when it needs something to dial.
            "phone": t.phone or "",
            "gps": t.gps_provider or "",
            "driver": t.driver or "",
            "effFrom": t.eff_from or "",
            "effTo": t.eff_to or "",
        }
    return out


def build_timing():
    """Visits and cycles, computed from the pings the providers delivered."""
    anchors = [{"id": a.id, "name": a.name, "polygon": a.polygon,
                "min_dwell_min": a.min_dwell_min} for a in Anchor.query.all()]
    roles = {a.role: a.id for a in Anchor.query.all() if a.role}
    pings = [{"plate": p.plate, "dt": p.dt, "lat": p.lat, "lng": p.lng,
              "speed": p.speed, "status": p.status}
             for p in GpsPing.query.order_by(GpsPing.dt).all()]
    deactivated = {engine.norm_plate(t.plate) for t in
                   Truck.query.filter_by(status="deactivated").all()}

    visits = engine.build_visits(pings, anchors, deactivated)
    sequences = engine.recompute_sequences(visits, roles)

    # The engine speaks snake_case, the tool camelCase. Nothing is recomputed
    # here - only renamed - so the Gantt and the Monitor agree on what happened.
    v_out = []
    for v in visits:
        enter, exit_ = _ms(v.get("enter")), _ms(v.get("exit"))
        v_out.append({
            "plate": v.get("plate"),
            "anchorId": v.get("anchor_id"),
            "anchorName": v.get("anchor_name"),
            "visitNum": v.get("visit_num"),
            "enter": enter,
            "exit": exit_,
            "durMs": (exit_ - enter) if (enter and exit_) else 0,
            "pingCount": v.get("ping_count", 0),
            "open": bool(v.get("open")),
        })

    CAMEL = {
        "cycle_date": "cycleDate", "xppl_in": "xpplIn", "xppl_out": "xpplOut",
        "loading_in": "loadingIn", "loading_out": "loadingOut",
        "lalay_out_in": "lalayOutIn", "lalay_out_out": "lalayOutOut",
        "ql49_out_in": "ql49OutIn", "ql49_out_out": "ql49OutOut",
        "chan_may_in": "chanMayIn", "chan_may_out": "chanMayOut",
        "ql49_back_in": "ql49BackIn", "ql49_back_out": "ql49BackOut",
        "detour_in": "detourIn", "detour_out": "detourOut",
        "lalay_back_in": "lalayBackIn", "lalay_back_out": "lalayBackOut",
        "xppl_r": "xpplR", "backhaul_type": "backhaulType",
    }
    s_out = []
    for s in sequences:
        row = {"plate": s.get("plate")}
        for k, val in s.items():
            if k == "plate":
                continue
            row[CAMEL.get(k, k)] = _ms(val) if isinstance(val, datetime) else val
        s_out.append(row)

    last = {}
    for p in pings:
        last[p["plate"]] = {"lat": p["lat"], "lng": p["lng"], "dt": _ms(p["dt"]),
                            "speed": p["speed"], "status": p["status"]}

    return {
        "visits": v_out,
        "sequences": s_out,
        # Where the data came from, in the shape the Data page lists uploads.
        "sources": [{"name": "GPS providers (live)", "kind": "api",
                     "visits": len(v_out), "uploads": 0}],
        "lastPings": last,
    }, len(pings)


def main():
    app = create_app()
    with app.app_context():
        fleet = build_fleet()
        n_fleet = _kv_set(FLEET_KEY, fleet)
        timing, n_pings = build_timing()
        n_timing = _kv_set(TIMING_KEY, timing)
        db.session.commit()
        print("fleet     %3d trucks   (%d bytes)" % (len(fleet), n_fleet))
        print("visits    %3d from %d pings" % (len(timing["visits"]), n_pings))
        print("cycles    %3d" % len(timing["sequences"]))
        print("timing blob %d bytes" % n_timing)


if __name__ == "__main__":
    main()
