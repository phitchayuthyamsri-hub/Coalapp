"""
JSON API. All endpoints require login. Data is shared across the team.
Uploads parse server-side and replace the relevant table.
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required
from sqlalchemy import func

from .models import (db, Truck, GpsPing, Anchor, RouteLeg,
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

