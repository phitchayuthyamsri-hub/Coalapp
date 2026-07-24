"""
Web routes for GPS capture (admin only):
  GET  /gps-capture           status page
  GET  /api/gps/status        JSON status (providers + per-truck last ping)
  POST /api/gps/pull/<prov>   trigger a one-off pull now (for testing)

All routes are admin-gated and side-effect-free until a provider is configured.
"""
from flask import Blueprint, render_template, jsonify, abort, current_app
from flask_login import login_required, current_user

from . import gps_ingest

bp = Blueprint("gps", __name__)

_PROVIDERS = ("tct", "adsun")


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
