"""
Web routes for GPS capture (admin only):
  GET  /gps-capture           status page
  GET  /api/gps/status        JSON status (providers + per-truck last ping)
  POST /api/gps/pull/<prov>   trigger a one-off pull now (for testing)

All routes are admin-gated and side-effect-free until a provider is configured.
"""
from datetime import datetime

from flask import Blueprint, render_template, jsonify, abort, current_app, request
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
    dl = (DailyList.query.filter_by(subcontractor_id=sub_id)
          .order_by(DailyList.list_date.desc()).first())
    if not dl:
        return set()
    return {(r.key or _eng.norm_plate(r.plate))
            for r in DailyListRow.query.filter_by(list_id=dl.id).all()}


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
