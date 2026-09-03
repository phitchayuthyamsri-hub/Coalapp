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


@bp.route("/gps-capture")
@login_required
def capture_page():
    _require_admin()
    return render_template("gps_capture.html")


@bp.get("/api/gps/status")
@login_required
def gps_status():
    _require_admin()
    return jsonify(gps_ingest.status_summary(current_app._get_current_object()))


@bp.get("/api/gps/points")
@login_required
def gps_points():
    _require_admin()
    return jsonify(gps_ingest.latest_points(current_app._get_current_object()))


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
    _require_admin()
    plate = (request.args.get("plate") or "").strip()
    source = (request.args.get("source") or "").strip()
    f = _parse_arg_dt(request.args.get("from"))
    t = _parse_arg_dt(request.args.get("to"))
    if not plate or not f or not t:
        return jsonify(ok=False, error="plate, from and to are required"), 400
    if t <= f:
        return jsonify(ok=False, error="'to' must be after 'from'"), 400
    return jsonify(gps_ingest.fetch_trail(current_app._get_current_object(), source, plate, f, t))
