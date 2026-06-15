"""
JSON API. All endpoints require login. Data is shared across the team.
Uploads parse server-side and replace the relevant table.
"""
import json
from functools import wraps
from flask import Blueprint, request, jsonify, abort
from flask_login import login_required, current_user
from sqlalchemy import func

from .models import (db, User, Truck, GpsPing, Anchor, RouteLeg, KVStore,
                     DispatchPlanRow, LoadActualRow, SubFleetRow)
from . import parsers, engine

bp = Blueprint("api", __name__, url_prefix="/api")


# ── Uploads ──────────────────────────────────────────────────────────────────
def _save_tmp():
    f = request.files.get("file")
    if not f:
        return None, (jsonify(error="no file"), 400)
    path = "/tmp/" + (f.filename or "upload.xlsx")
    f.save(path)
    return path, None


@bp.post("/upload/gps")
@login_required
def upload_gps():
    path, err = _save_tmp()
    if err:
        return err
    pings = parsers.parse_gps(path)
    if request.args.get("replace") == "1":
        GpsPing.query.delete()
    for p in pings:
        db.session.add(GpsPing(plate=p["plate"], dt=p["dt"], lat=p["lat"],
                               lng=p["lng"], speed=p["speed"],
                               status=p["status"], source=p["source"]))
    db.session.commit()
    return jsonify(added=len(pings))


@bp.post("/upload/plan")
@login_required
def upload_plan():
    path, err = _save_tmp()
    if err:
        return err
    rows = parsers.parse_dispatch_plan(path)
    DispatchPlanRow.query.delete()
    for r in rows:
        db.session.add(DispatchPlanRow(plate=r["plate"], key=r["key"],
                                       load_start=r["load_start"],
                                       port_arrive=r["port_arrive"]))
    db.session.commit()
    return jsonify(added=len(rows))


@bp.post("/upload/load")
@login_required
def upload_load():
    path, err = _save_tmp()
    if err:
        return err
    rows = parsers.parse_load_actual(path)
    LoadActualRow.query.delete()
    for r in rows:
        db.session.add(LoadActualRow(plate=r["plate"], key=r["key"],
                                     load_in=r["load_in"], net=r["net"],
                                     ticket=r["ticket"]))
    db.session.commit()
    return jsonify(added=len(rows))


@bp.post("/upload/subfleet")
@login_required
def upload_subfleet():
    path, err = _save_tmp()
    if err:
        return err
    rows = parsers.parse_subfleet(path)
    SubFleetRow.query.delete()
    for r in rows:
        db.session.add(SubFleetRow(plate=r["plate"], key=r["key"],
                                   declared_haul=r["declared_haul"],
                                   claimed_arrive_mine=r["claimed_arrive_mine"]))
    db.session.commit()
    return jsonify(added=len(rows))


# ── Fleet ────────────────────────────────────────────────────────────────────
@bp.get("/fleet")
@login_required
def fleet():
    trucks = Truck.query.order_by(Truck.plate).all()
    return jsonify([{"plate": t.plate, "status": t.status, "phone": t.phone,
                     "gps_provider": t.gps_provider, "eff_from": t.eff_from,
                     "eff_to": t.eff_to} for t in trucks])


@bp.post("/fleet")
@login_required
def fleet_upsert():
    d = request.get_json(force=True)
    plate = engine.norm_plate(d.get("plate"))
    if not plate:
        return jsonify(error="plate required"), 400
    t = Truck.query.filter_by(plate=plate).first() or Truck(plate=plate)
    t.status = d.get("status", t.status or "online")
    t.phone = d.get("phone", t.phone or "")
    t.gps_provider = d.get("gps_provider", t.gps_provider or "")
    t.eff_from = d.get("eff_from", t.eff_from or "")
    t.eff_to = d.get("eff_to", t.eff_to or "")
    db.session.add(t)
    db.session.commit()
    return jsonify(ok=True)


@bp.delete("/fleet/<plate>")
@login_required
def fleet_delete(plate):
    t = Truck.query.filter_by(plate=engine.norm_plate(plate)).first()
    if t:
        db.session.delete(t)
        db.session.commit()
    return jsonify(ok=True)


# ── Anchors & routes (read for map; write for config) ────────────────────────
@bp.get("/anchors")
@login_required
def anchors():
    return jsonify([{"id": a.id, "name": a.name, "color": a.color,
                     "category": a.category, "role": a.role,
                     "polygon": a.polygon, "min_dwell_min": a.min_dwell_min}
                    for a in Anchor.query.all()])


@bp.get("/routes")
@login_required
def routes():
    return jsonify([{"leg_key": r.leg_key, "label": r.label,
                     "points": r.points, "speed": r.speed}
                    for r in RouteLeg.query.all()])


@bp.put("/routes/<leg_key>")
@login_required
def route_update(leg_key):
    d = request.get_json(force=True)
    r = RouteLeg.query.filter_by(leg_key=leg_key).first()
    if not r:
        return jsonify(error="unknown leg"), 404
    if "points" in d:
        r.points = d["points"]
    if "speed" in d and d["speed"]:
        r.speed = float(d["speed"])
    db.session.commit()
    return jsonify(ok=True)


# ── Status (the engine output) ───────────────────────────────────────────────
def _last_pings():
    """Latest ping per plate."""
    sub = (db.session.query(GpsPing.plate, func.max(GpsPing.dt).label("mx"))
           .group_by(GpsPing.plate).subquery())
    q = (db.session.query(GpsPing)
         .join(sub, (GpsPing.plate == sub.c.plate) & (GpsPing.dt == sub.c.mx)))
    out = {}
    for p in q:
        out[p.plate] = {"lat": p.lat, "lng": p.lng, "dt": p.dt,
                        "speed": p.speed, "status": p.status}
    return out


@bp.get("/status")
@login_required
def status():
    anchors = [{"id": a.id, "name": a.name, "polygon": a.polygon,
                "min_dwell_min": a.min_dwell_min} for a in Anchor.query.all()]
    roles = {a.role: a.id for a in Anchor.query.all() if a.role}
    routes = {r.leg_key: {"points": r.points, "speed": r.speed}
              for r in RouteLeg.query.all()}

    pings = [{"plate": p.plate, "dt": p.dt, "lat": p.lat, "lng": p.lng,
              "speed": p.speed, "status": p.status}
             for p in GpsPing.query.order_by(GpsPing.dt).all()]

    deactivated = {engine.norm_plate(t.plate) for t in
                   Truck.query.filter_by(status="deactivated").all()}

    visits = engine.build_visits(pings, anchors, deactivated)
    sequences = engine.recompute_sequences(visits, roles)

    plates = set(t.plate for t in Truck.query.all())
    plates |= set(p["plate"] for p in pings)
    plates -= {p for p in plates if engine.norm_plate(p) in deactivated}

    last_pings = _last_pings()
    plan = [{"plate": r.plate, "key": r.key, "load_start": r.load_start,
             "port_arrive": r.port_arrive} for r in DispatchPlanRow.query.all()]
    load = [{"plate": r.plate, "key": r.key, "load_in": r.load_in,
             "net": r.net, "ticket": r.ticket} for r in LoadActualRow.query.all()]

    rows = engine.build_status_rows(list(plates), last_pings, sequences, routes,
                                    anchors, roles, plan, load, deactivated)
    return jsonify(rows=rows, count=len(rows))

# ── Visits (for the Timeline page) ───────────────────────────────────────────
@bp.get("/visits")
@login_required
def visits():
    from datetime import datetime, timedelta
    anchors = [{"id": a.id, "name": a.name, "polygon": a.polygon,
                "min_dwell_min": a.min_dwell_min} for a in Anchor.query.all()]
    role_by_anchor = {a.id: a.role for a in Anchor.query.all() if a.role}

    q = GpsPing.query
    fr = request.args.get("from")
    to = request.args.get("to")
    plate = request.args.get("plate")
    if fr:
        q = q.filter(GpsPing.dt >= datetime.strptime(fr, "%Y-%m-%d"))
    if to:
        q = q.filter(GpsPing.dt < datetime.strptime(to, "%Y-%m-%d") + timedelta(days=1))
    if plate:
        q = q.filter(GpsPing.plate == plate)
    pings = [{"plate": p.plate, "dt": p.dt, "lat": p.lat, "lng": p.lng,
              "speed": p.speed, "status": p.status}
             for p in q.order_by(GpsPing.dt).all()]

    deactivated = {engine.norm_plate(t.plate) for t in
                   Truck.query.filter_by(status="deactivated").all()}
    vs = engine.build_visits(pings, anchors, deactivated)

    out, mn, mx = [], None, None
    for v in vs:
        e, x = v["enter"], v.get("exit") or v["enter"]
        if mn is None or e < mn:
            mn = e
        if mx is None or x > mx:
            mx = x
        out.append({
            "plate": v["plate"], "anchor_name": v["anchor_name"],
            "role": role_by_anchor.get(v["anchor_id"], ""),
            "enter": e.isoformat(), "exit": x.isoformat(),
            "dur_min": round((x - e).total_seconds() / 60),
            "open": bool(v.get("open")),
        })
    return jsonify(visits=out,
                   min=mn.isoformat() if mn else None,
                   max=mx.isoformat() if mx else None)

# ── Plan vs Actual ───────────────────────────────────────────────────────────
@bp.get("/pva")
@login_required
def pva():
    anchors = [{"id": a.id, "name": a.name, "polygon": a.polygon,
                "min_dwell_min": a.min_dwell_min} for a in Anchor.query.all()]
    roles = {a.role: a.id for a in Anchor.query.all() if a.role}
    pings = [{"plate": p.plate, "dt": p.dt, "lat": p.lat, "lng": p.lng,
              "speed": p.speed, "status": p.status}
             for p in GpsPing.query.order_by(GpsPing.dt).all()]
    deactivated = {engine.norm_plate(t.plate) for t in
                   Truck.query.filter_by(status="deactivated").all()}
    visits = engine.build_visits(pings, anchors, deactivated)
    seqs = engine.recompute_sequences(visits, roles)
    plan = DispatchPlanRow.query.all()

    THRESH = 60  # minutes; on-time window is +/- 1 hour
    rows, scored, ontime = [], 0, 0
    for p in plan:
        cyc = [c for c in seqs if engine.norm_plate_strict(c["plate"]) == p.key]
        chosen = None
        if cyc and p.load_start:
            same = [c for c in cyc if c["xppl_in"]
                    and c["xppl_in"].date() == p.load_start.date()]
            if same:
                chosen = same[0]
            else:
                chosen = min(cyc, key=lambda c: abs((c["xppl_in"] - p.load_start).total_seconds())
                             if c["xppl_in"] else 9e18)
        elif cyc:
            chosen = sorted(cyc, key=lambda c: c["cycle_date"])[-1]

        actual_load = (chosen.get("loading_in") or chosen.get("xppl_in")) if chosen else None
        actual_port = chosen.get("chan_may_in") if chosen else None

        port_delta, status, code = None, "no actual yet", "na"
        if actual_port and p.port_arrive:
            port_delta = round((actual_port - p.port_arrive).total_seconds() / 60)
            scored += 1
            if port_delta < -THRESH:
                status, code = "early", "planned"
                ontime += 1
            elif port_delta > THRESH:
                status, code = "late", "unassigned"
            else:
                status, code = "on-time", "reloaded"
                ontime += 1
        elif actual_port:
            status, code = "actual only", "fronthaul"

        rows.append({
            "plate": p.plate,
            "plan_load": engine.fmt(p.load_start),
            "actual_load": engine.fmt(actual_load),
            "plan_port": engine.fmt(p.port_arrive),
            "actual_port": engine.fmt(actual_port),
            "port_delta": port_delta,
            "status": status, "code": code,
        })
    pct = round(ontime / scored * 100) if scored else None
    return jsonify(rows=rows, ontime_pct=pct, scored=scored, total=len(rows))

# ── Shared engine state for analytics endpoints ──────────────────────────────
def _engine_state():
    anchors = [{"id": a.id, "name": a.name, "polygon": a.polygon,
                "min_dwell_min": a.min_dwell_min} for a in Anchor.query.all()]
    roles = {a.role: a.id for a in Anchor.query.all() if a.role}
    routes = {r.leg_key: {"points": r.points, "speed": r.speed}
              for r in RouteLeg.query.all()}
    pings = [{"plate": p.plate, "dt": p.dt, "lat": p.lat, "lng": p.lng,
              "speed": p.speed, "status": p.status}
             for p in GpsPing.query.order_by(GpsPing.dt).all()]
    deactivated = {engine.norm_plate(t.plate) for t in
                   Truck.query.filter_by(status="deactivated").all()}
    visits = engine.build_visits(pings, anchors, deactivated)
    seqs = engine.recompute_sequences(visits, roles)
    return {"anchors": anchors, "roles": roles, "routes": routes,
            "pings": pings, "deactivated": deactivated,
            "visits": visits, "seqs": seqs}


def _status_rows(st):
    plates = set(t.plate for t in Truck.query.all()) | set(p["plate"] for p in st["pings"])
    plates -= {p for p in plates if engine.norm_plate(p) in st["deactivated"]}
    plan = [{"plate": r.plate, "key": r.key, "load_start": r.load_start,
             "port_arrive": r.port_arrive} for r in DispatchPlanRow.query.all()]
    load = [{"plate": r.plate, "key": r.key, "load_in": r.load_in,
             "net": r.net, "ticket": r.ticket} for r in LoadActualRow.query.all()]
    return engine.build_status_rows(list(plates), _last_pings(), st["seqs"],
                                    st["routes"], st["anchors"], st["roles"],
                                    plan, load, st["deactivated"])


# ── Subcontractor fleet status ───────────────────────────────────────────────
@bp.get("/subfleet")
@login_required
def subfleet():
    st = _engine_state()
    rows_by_plate = {engine.norm_plate_strict(r["plate"]): r for r in _status_rows(st)}
    out = []
    for r in SubFleetRow.query.all():
        sr = rows_by_plate.get(r.key)
        haul = sr["haul"] if sr else "-"
        est = sr["eta_criteria"] if (sr and sr["haul"] == "Backhaul") else ""
        last_seen = sr["last_seen"] if sr else ""
        if not last_seen:
            gps = "No GPS"
        elif haul == "Backhaul":
            gps = "Returning"
        elif haul == "Completed":
            gps = "At mine"
        else:
            gps = "Not returning"
        delta = None
        if est and r.claimed_arrive_mine:
            from datetime import datetime
            try:
                e = datetime.strptime(est, "%Y-%m-%d %H:%M")
                delta = round((e - r.claimed_arrive_mine).total_seconds() / 60)
            except Exception:
                delta = None
        out.append({
            "plate": r.plate, "declared_haul": r.declared_haul or "",
            "status": haul, "location": (sr["direction"] if sr else ""),
            "claimed_arrive_mine": engine.fmt(r.claimed_arrive_mine),
            "est_arrive_mine": est, "delta": delta, "gps_check": gps,
        })
    return jsonify(rows=out, count=len(out))


# ── Performance dashboard ────────────────────────────────────────────────────
@bp.get("/performance")
@login_required
def performance():
    st = _engine_state()
    seqs = st["seqs"]
    completed = [c for c in seqs if c["chan_may_in"]]
    # cycle time = xppl_in -> xppl_r (next mine arrival)
    durs = []
    for c in seqs:
        if c["xppl_in"] and c["xppl_r"]:
            durs.append((c["xppl_r"] - c["xppl_in"]).total_seconds() / 3600.0)
    avg_cycle = round(sum(durs) / len(durs), 1) if durs else None
    rows = _status_rows(st)
    by_haul = {}
    for r in rows:
        by_haul[r["haul"]] = by_haul.get(r["haul"], 0) + 1
    return jsonify(
        trucks=len(rows),
        cycles=len(seqs),
        completed_trips=len(completed),
        avg_cycle_hours=avg_cycle,
        plan_cycle_hours=48,
        by_haul=by_haul,
    )


# ── Daily performance ────────────────────────────────────────────────────────
@bp.get("/daily")
@login_required
def daily():
    st = _engine_state()
    ports = {}
    for c in st["seqs"]:
        if c["chan_may_in"]:
            d = c["chan_may_in"].date().isoformat()
            ports[d] = ports.get(d, 0) + 1
    loads = {}
    tonnes = {}
    for r in LoadActualRow.query.all():
        if r.load_in:
            d = r.load_in.date().isoformat()
            loads[d] = loads.get(d, 0) + 1
            if r.net:
                tonnes[d] = round(tonnes.get(d, 0) + r.net / 1000.0, 1)
    days = sorted(set(list(ports) + list(loads)))
    series = [{"date": d, "port_arrivals": ports.get(d, 0),
               "loads": loads.get(d, 0), "tonnes": tonnes.get(d, 0)} for d in days]
    return jsonify(series=series)

# ── Data tables for the Data-input pages ─────────────────────────────────────
@bp.get("/sequences")
@login_required
def sequences():
    st = _engine_state()
    def f(x): return engine.fmt(x)
    rows = []
    for c in st["seqs"]:
        rows.append({
            "plate": c["plate"], "cycle_date": f(c["cycle_date"]),
            "xppl_in": f(c["xppl_in"]), "loading_in": f(c["loading_in"]),
            "lalay_out_in": f(c["lalay_out_in"]), "ql49_out_in": f(c["ql49_out_in"]),
            "chan_may_in": f(c["chan_may_in"]), "ql49_back_in": f(c["ql49_back_in"]),
            "lalay_back_in": f(c["lalay_back_in"]), "xppl_r": f(c["xppl_r"]),
            "backhaul_type": c["backhaul_type"] or "",
            "complete": bool(c["chan_may_in"] and c["xppl_r"]),
        })
    return jsonify(rows=rows, count=len(rows))


@bp.get("/gps_summary")
@login_required
def gps_summary():
    from sqlalchemy import func
    q = (db.session.query(GpsPing.plate, func.count(GpsPing.id),
                          func.min(GpsPing.dt), func.max(GpsPing.dt))
         .group_by(GpsPing.plate).order_by(GpsPing.plate))
    rows = [{"plate": p, "pings": n, "first": engine.fmt(mn), "last": engine.fmt(mx)}
            for p, n, mn, mx in q]
    total = sum(r["pings"] for r in rows)
    return jsonify(rows=rows, total_pings=total, plates=len(rows))


@bp.get("/plan_rows")
@login_required
def plan_rows():
    rows = [{"plate": r.plate, "load_start": engine.fmt(r.load_start),
             "port_arrive": engine.fmt(r.port_arrive)}
            for r in DispatchPlanRow.query.order_by(DispatchPlanRow.load_start).all()]
    return jsonify(rows=rows, count=len(rows))


@bp.get("/load_rows")
@login_required
def load_rows():
    rows = [{"plate": r.plate, "load_in": engine.fmt(r.load_in),
             "net": r.net, "ticket": r.ticket}
            for r in LoadActualRow.query.order_by(LoadActualRow.load_in).all()]
    return jsonify(rows=rows, count=len(rows))


@bp.get("/truckstatus")
@login_required
def truckstatus():
    """Pivot: plate (rows) x date (cols). Cell = that day's key events."""
    st = _engine_state()
    # collect events per (plate, date)
    cells = {}
    dates = set()

    def add(plate, dt, label):
        if not dt:
            return
        d = dt.date().isoformat()
        dates.add(d)
        cells.setdefault(plate, {}).setdefault(d, [])
        cells[plate][d].append((dt, label))

    for c in st["seqs"]:
        add(c["plate"], c["loading_in"], "Load")
        add(c["plate"], c["lalay_out_in"], "Border")
        add(c["plate"], c["chan_may_in"], "Port")
        add(c["plate"], c["lalay_back_in"], "Return")
        add(c["plate"], c["xppl_r"], "Mine")

    plates = sorted(cells.keys())
    dates = sorted(dates)
    out = {}
    for plate in plates:
        out[plate] = {}
        for d in dates:
            evs = sorted(cells[plate].get(d, []))
            out[plate][d] = " · ".join(f"{lbl} {dt.strftime('%H:%M')}" for dt, lbl in evs)
    return jsonify(plates=plates, dates=dates, cells=out)


@bp.put("/anchors/<int:aid>")
@login_required
def anchor_update(aid):
    a = db.session.get(Anchor, aid)
    if not a:
        return jsonify(error="not found"), 404
    d = request.get_json(force=True)
    if "role" in d:
        a.role = d["role"] or ""
    if "min_dwell_min" in d and d["min_dwell_min"] is not None:
        a.min_dwell_min = int(d["min_dwell_min"])
    db.session.commit()
    return jsonify(ok=True)


# ── Shared key-value store (backs the full tool's localStorage) ──────────────
@bp.get("/kv")
@login_required
def kv_all():
    return jsonify({r.key: r.value for r in KVStore.query.all()})


@bp.put("/kv/<path:key>")
@login_required
def kv_put(key):
    d = request.get_json(force=True, silent=True) or {}
    val = d.get("value", "")
    row = db.session.get(KVStore, key)
    if row is None:
        row = KVStore(key=key, value=val)
        db.session.add(row)
    else:
        row.value = val
    db.session.commit()
    return jsonify(ok=True)


@bp.delete("/kv/<path:key>")
@login_required
def kv_delete(key):
    row = db.session.get(KVStore, key)
    if row is not None:
        db.session.delete(row)
        db.session.commit()
    return jsonify(ok=True)


# ── Access control: identity + admin-managed tab access ──────────────────────
TAB_KEYS = ["perf","daily","pva","subfleet","anchors","data","gps","plan",
            "truckstatus","weigh","fleet","guide"]


def _tabs_of(u):
    if not u.allowed_tabs:
        return None  # None = all tabs allowed
    try:
        return [t for t in json.loads(u.allowed_tabs) if t in TAB_KEYS]
    except Exception:
        return None


def admin_required(f):
    @wraps(f)
    @login_required
    def w(*a, **k):
        if not getattr(current_user, "is_admin", False):
            abort(403)
        return f(*a, **k)
    return w


@bp.get("/me")
@login_required
def me():
    return jsonify(username=current_user.username,
                   is_admin=bool(current_user.is_admin),
                   tabs=_tabs_of(current_user))


@bp.get("/admin/users")
@admin_required
def admin_users():
    out = []
    for u in User.query.order_by(User.id.asc()).all():
        out.append({"id": u.id, "username": u.username,
                    "is_admin": bool(u.is_admin), "tabs": _tabs_of(u)})
    return jsonify(out)


@bp.put("/admin/users/<int:uid>")
@admin_required
def admin_update(uid):
    u = db.session.get(User, uid)
    if not u:
        abort(404)
    d = request.get_json(force=True, silent=True) or {}
    if "is_admin" in d:
        u.is_admin = bool(d["is_admin"])
    if "tabs" in d:
        t = d["tabs"]
        if t is None:
            u.allowed_tabs = None
        else:
            u.allowed_tabs = json.dumps([str(x) for x in t if str(x) in TAB_KEYS])
    db.session.commit()
    # Safety net: never leave the system with zero admins.
    if not User.query.filter_by(is_admin=True).first():
        u.is_admin = True
        db.session.commit()
        return jsonify(ok=True, note="At least one admin is required; kept this user as admin.")
    return jsonify(ok=True, tabs=_tabs_of(u), is_admin=bool(u.is_admin))
