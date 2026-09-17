"""
Web routes for GPS capture (admin only):
  GET  /gps-capture           status page
  GET  /api/gps/status        JSON status (providers + per-truck last ping)
  POST /api/gps/pull/<prov>   trigger a one-off pull now (for testing)

All routes are admin-gated and side-effect-free until a provider is configured.
"""
from datetime import datetime

from flask import (Blueprint, render_template, jsonify, abort, current_app,
                   request, Response)
from flask_login import login_required, current_user

from . import gps_ingest

bp = Blueprint("gps", __name__)


@bp.after_request
def _no_store(resp):
    """Provider status and positions change every few minutes, and a cached
    answer is indistinguishable from a broken integration: the page showed all
    three providers OFF while the server had them enabled and pulling. Every
    other blueprint already says no-store; this one was the exception."""
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

_PROVIDERS = ("tct", "viettel", "adsun")


def _parse_arg_dt(v):
    if not v:
        return None
    s = str(v).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None


def _require_admin():
    if not getattr(current_user, "is_admin", False):
        abort(403)


# Reading a truck's positions is part of checking a declaration, so the people
# who review one can do it. Pulling from a provider, or poking a provider's API,
# stays admin: those act on somebody else's system.
def _require_gps_read():
    """Everyone logged in may look at positions. Pulling still needs an admin."""
    return


def _gps_scope():
    """The plates this login may see, or None for all of them.

    A subcontractor is scoped to its own trucks here exactly as it is
    everywhere else. The page lists every truck on the GPS account, and one
    company being handed another company's positions is the thing the whole
    per-company scoping exists to prevent - so the rule holds on this page too
    rather than being an exception nobody remembers.
    """
    if getattr(current_user, "is_admin", False):
        return None
    if (getattr(current_user, "role", "") or "").lower() != "subcontractor":
        return None
    sub_id = getattr(current_user, "subcontractor_id", None)
    from .models import DailyList, DailyListRow
    from . import engine as _eng
    if sub_id is None:
        return set()                      # scoped to a company they do not have
    # Every list this company has ever sent, not just the newest. A truck that
    # was off the sheet yesterday is still one of theirs, and scoping to the
    # last list alone hid trucks from the company that owns them.
    ids = [d.id for d in DailyList.query.filter_by(subcontractor_id=sub_id).all()]
    if not ids:
        return set()
    return {(r.key or _eng.norm_plate(r.plate))
            for r in DailyListRow.query.filter(DailyListRow.list_id.in_(ids)).all()}


def _in_scope(plate, scope):
    if scope is None:
        return True
    from . import engine as _eng
    return _eng.norm_plate(plate) in scope


@bp.route("/gps-capture")
@login_required
def capture_page():
    _require_gps_read()
    return render_template("gps_capture.html",
                           maps_key=current_app.config.get("GOOGLE_MAPS_KEY", ""))


@bp.route("/truck-trail")
@login_required
def truck_trail_page():
    """One truck, one day and a bit, on its own page.

    The capture page is a control room: every provider, every truck, a pull
    button. Somebody checking a single declaration wants none of that - they
    want that truck, yesterday to now, and nothing else on the screen to read.
    """
    from .models import GpsPing
    from . import engine as _eng
    plate = (request.args.get("plate") or "").strip()
    if not plate:
        abort(404)
    if not _in_scope(plate, _gps_scope()):
        abort(403)
    # Which provider last saw it, so the page does not have to ask.
    key = _eng.norm_plate(plate)
    src = ""
    for g in (GpsPing.query.order_by(GpsPing.dt.desc()).limit(4000).all()):
        if _eng.norm_plate(g.plate) == key:
            src = g.source or ""
            break
    return render_template("truck_trail.html", plate=plate, source=src,
                           maps_key=current_app.config.get("GOOGLE_MAPS_KEY", ""))


@bp.get("/api/gps/status")
@login_required
def gps_status():
    _require_gps_read()
    d = gps_ingest.status_summary(current_app._get_current_object())
    scope = _gps_scope()
    if scope is not None:
        d["trucks"] = [t for t in (d.get("trucks") or [])
                       if _in_scope(t.get("plate"), scope)]
    return jsonify(d)


@bp.get("/api/gps/points")
@login_required
def gps_points():
    _require_gps_read()
    pts = gps_ingest.latest_points(current_app._get_current_object())
    scope = _gps_scope()
    if scope is not None and isinstance(pts, list):
        pts = [p for p in pts if _in_scope(p.get("plate"), scope)]
    return jsonify(pts)


@bp.post("/api/gps/pull/<provider>")
@login_required
def gps_pull(provider):
    _require_admin()
    if provider not in _PROVIDERS:
        abort(404)
    res = gps_ingest.run_provider(current_app._get_current_object(), provider)
    return jsonify(res)


@bp.post("/api/gps/debug/<provider>")
@login_required
def gps_debug(provider):
    _require_admin()
    if provider not in _PROVIDERS:
        abort(404)
    return jsonify(gps_ingest.debug_provider(current_app._get_current_object(), provider))


@bp.get("/api/gps/export.xlsx")
@login_required
def gps_export():
    """The STORED positions as a workbook - what this system has captured,
    not a live pull. One truck, or every truck this login may see, over a
    window. The same scoping as the rest of the GPS pages holds: a company
    exports its own trucks and nobody else's."""
    _require_gps_read()
    import io
    import openpyxl
    from openpyxl.styles import Font
    from .models import GpsPing
    from . import engine as _eng

    plate = (request.args.get("plate") or "").strip()
    scope = _gps_scope()
    if plate and not _in_scope(plate, scope):
        return jsonify(ok=False, error="That truck is not on your fleet."), 403
    f = _parse_arg_dt(request.args.get("from"))
    t = _parse_arg_dt(request.args.get("to"))
    if not f or not t:
        return jsonify(ok=False, error="from and to are required"), 400
    if t <= f:
        return jsonify(ok=False, error="'to' must be after 'from'"), 400

    key = _eng.norm_plate(plate) if plate else None
    out = []
    for g in (GpsPing.query.filter(GpsPing.dt >= f, GpsPing.dt <= t)
              .order_by(GpsPing.plate, GpsPing.dt).all()):
        if key is not None and _eng.norm_plate(g.plate) != key:
            continue
        if key is None and scope is not None \
                and _eng.norm_plate(g.plate) not in scope:
            continue
        out.append(g)
        if len(out) > 100000:
            return jsonify(ok=False,
                           error="Over 100,000 positions in that window. "
                                 "Narrow the dates or pick one truck."), 400
    if not out:
        return jsonify(ok=False, error="No stored positions in that window. "
                       "The provider is pulled every few minutes - a quiet "
                       "stretch means nothing was collected."), 404

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "GPS positions"
    ws.append(["Captured GPS positions — %s — %s to %s"
               % (plate or "all trucks", f.strftime("%d/%m/%Y %H:%M"),
                  t.strftime("%d/%m/%Y %H:%M"))])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append(["Times are local (UTC+7), as the providers report them. These "
               "are the positions this system captured, not a live pull."])
    ws["A2"].font = Font(italic=True, size=9)
    ws.append([])
    ws.append(["No", "Plate", "Time", "Latitude", "Longitude",
               "Speed (km/h)", "Status", "Source"])
    head = Font(bold=True)
    for c in ws[4]:
        c.font = head
    for i, g in enumerate(out, 1):
        ws.append([i, g.plate, g.dt, g.lat, g.lng, g.speed,
                   g.status or "", (g.source or "").replace("api:", "")])
    for col, w in zip("ABCDEFGH", (7, 12, 19, 11, 11, 12, 14, 10)):
        ws.column_dimensions[col].width = w
    for cell in ws["C"][4:]:
        cell.number_format = "dd/mm/yyyy hh:mm:ss"
    ws.freeze_panes = "A5"
    ws.auto_filter.ref = "A4:H%d" % (4 + len(out))

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    name = "gps_%s_%s_%s.xlsx" % ((plate or "all").replace(" ", ""),
                                  f.strftime("%Y%m%d%H%M"),
                                  t.strftime("%Y%m%d%H%M"))
    return Response(buf.read(),
                    mimetype="application/vnd.openxmlformats-officedocument."
                             "spreadsheetml.sheet",
                    headers={"Content-Disposition":
                             'attachment; filename="%s"' % name})


@bp.get("/api/gps/trail")
@login_required
def gps_trail():
    _require_gps_read()
    plate = (request.args.get("plate") or "").strip()
    source = (request.args.get("source") or "").strip()
    if not _in_scope(plate, _gps_scope()):
        return jsonify(ok=False, error="That truck is not on your fleet."), 403
    f = _parse_arg_dt(request.args.get("from"))
    t = _parse_arg_dt(request.args.get("to"))
    if not plate or not f or not t:
        return jsonify(ok=False, error="plate, from and to are required"), 400
    if t <= f:
        return jsonify(ok=False, error="'to' must be after 'from'"), 400
    return jsonify(gps_ingest.fetch_trail(current_app._get_current_object(), source, plate, f, t))
