"""
WI LA-NT-001 endpoints — return-route selection (§5.3) and route windows (§4).

  GET  /api/wi/windows                 window + route definitions (single source of truth)
  GET  /api/wi/route?date=YYYY-MM-DD   saved selections for a plan date
  POST /api/wi/route                   set/update one truck's return route + cost
  POST /api/wi/route/approve           approve a date's selections (records the name)
  GET  /api/wi/route/export.xlsx       the validated list as Excel

Selection requires an editor account; approval records whoever approves, since
the WI requires a name against the confirmed list ("no verbal confirmations").
"""
import io
from datetime import datetime

from flask import Blueprint, jsonify, request, abort, Response
from flask_login import login_required, current_user

from .models import db, ReturnRoute
from . import wi_rules

bp = Blueprint("wi", __name__, url_prefix="/api/wi")


def _editor_required():
    if getattr(current_user, "can_edit", True) is False:
        abort(403)


def _row(r):
    return {
        "plate": r.plate, "key": r.key, "date": r.plan_date,
        "route": r.route or wi_rules.DEFAULT_ROUTE,
        "cost": r.cost_variance,
        "note": r.note or "",
        "set_by": r.set_by or "", "set_at": r.set_at.strftime("%Y-%m-%d %H:%M") if r.set_at else "",
        "approved_by": r.approved_by or "",
        "approved_at": r.approved_at.strftime("%Y-%m-%d %H:%M") if r.approved_at else "",
    }


@bp.get("/windows")
@login_required
def windows():
    return jsonify(windows=wi_rules.WINDOWS, routes=wi_rules.ROUTES,
                   default_route=wi_rules.DEFAULT_ROUTE,
                   binding_gate=wi_rules.BINDING_GATE)


@bp.get("/route")
@login_required
def route_list():
    d = (request.args.get("date") or "").strip()
    q = ReturnRoute.query
    if d:
        q = q.filter_by(plan_date=d)
    rows = q.order_by(ReturnRoute.plate.asc()).all()
    return jsonify(rows=[_row(r) for r in rows], count=len(rows))


@bp.post("/route")
@login_required
def route_set():
    _editor_required()
    d = request.get_json(force=True, silent=True) or {}
    plate = str(d.get("plate") or "").strip()
    date = str(d.get("date") or "").strip()
    route = str(d.get("route") or wi_rules.DEFAULT_ROUTE).strip().lower()
    if not plate or not date:
        return jsonify(ok=False, error="plate and date are required"), 400
    if route not in wi_rules.ROUTE_KEYS:
        return jsonify(ok=False, error="route must be one of " + ", ".join(wi_rules.ROUTE_KEYS)), 400
    cost = d.get("cost")
    try:
        cost = float(cost) if cost not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify(ok=False, error="cost must be a number"), 400

    key = wi_rules.norm_plate(plate)
    r = ReturnRoute.query.filter_by(key=key, plan_date=date).first()
    if not r:
        r = ReturnRoute(plate=plate, key=key, plan_date=date)
        db.session.add(r)
    r.plate = plate
    r.route = route
    r.cost_variance = cost
    r.note = str(d.get("note") or "")[:300]
    r.set_by = getattr(current_user, "username", "")
    r.set_at = datetime.utcnow()
    # Changing a selection invalidates a previous approval — it must be re-approved.
    r.approved_by = None
    r.approved_at = None
    db.session.commit()
    return jsonify(ok=True, row=_row(r))


@bp.post("/route/approve")
@login_required
def route_approve():
    _editor_required()
    d = request.get_json(force=True, silent=True) or {}
    date = str(d.get("date") or "").strip()
    if not date:
        return jsonify(ok=False, error="date is required"), 400
    rows = ReturnRoute.query.filter_by(plan_date=date).all()
    if not rows:
        return jsonify(ok=False, error="nothing to approve for " + date), 400
    who = getattr(current_user, "username", "")
    now = datetime.utcnow()
    for r in rows:
        r.approved_by = who
        r.approved_at = now
    db.session.commit()
    return jsonify(ok=True, approved=len(rows), by=who,
                   at=now.strftime("%Y-%m-%d %H:%M"))


@bp.get("/route/export.xlsx")
@login_required
def route_export():
    import openpyxl
    date = (request.args.get("date") or "").strip()
    q = ReturnRoute.query
    if date:
        q = q.filter_by(plan_date=date)
    rows = q.order_by(ReturnRoute.plan_date.asc(), ReturnRoute.plate.asc()).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Return route"
    ws.append(["Plan date", "Plate", "Return route", "Cycle (h)", "Cost variance",
               "Note", "Set by", "Set at", "Approved by", "Approved at"])
    cyc = {r["key"]: r["cycle_hours"] for r in wi_rules.ROUTES}
    lbl = {r["key"]: r["label"] for r in wi_rules.ROUTES}
    for r in rows:
        ws.append([r.plan_date, r.plate, lbl.get(r.route, r.route), cyc.get(r.route),
                   r.cost_variance, r.note or "", r.set_by or "",
                   r.set_at.strftime("%Y-%m-%d %H:%M") if r.set_at else "",
                   r.approved_by or "",
                   r.approved_at.strftime("%Y-%m-%d %H:%M") if r.approved_at else ""])
    for col, w in zip("ABCDEFGHIJ", (12, 14, 14, 10, 14, 30, 16, 17, 16, 17)):
        ws.column_dimensions[col].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    name = "return_route_" + (date or "all") + ".xlsx"
    return Response(buf.read(),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="' + name + '"'})
