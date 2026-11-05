"""Data issues: what the subcontractors sent wrong or left out, kept on record.

05/11/2026 (user): truck and driver lists are entered exactly as the companies
send them - a blank stays blank, a broken number stays broken - so that the gap
costs the company that left it. What makes that work is a record: when the
missing contact is needed, the date it was first reported and the file it came
in are already written down, and nobody loses time digging for them.

    /data-issues                     the page (also inside the tool, Truck menu)
    GET  /api/data-issues            the list, newest first
    POST /api/data-issues            log one          (admin)
    POST /api/data-issues/<id>       change / fix one (admin)

Admin only, reading and writing.
"""
from datetime import datetime

from flask import Blueprint, jsonify, request, abort, render_template
from flask_login import login_required, current_user

from .models import db, DataIssue, Subcontractor

bp = Blueprint("data_issues", __name__)

KINDS = ("phone", "driver", "trailer", "plate", "gps", "list", "other")
# Admin eyes only (user 05/11/2026) - not the planners, not the monitors,
# and never the companies it is about.
VIEWERS = ("admin",)


def _role():
    return (getattr(current_user, "role", "") or "").lower()


def _may_view():
    return _role() in VIEWERS


def _may_edit():
    return _role() == "admin"


def _day(v):
    v = (v or "").strip()[:10]
    try:
        datetime.strptime(v, "%Y-%m-%d")
        return v
    except ValueError:
        return ""


def _out(i, subs):
    return {"id": i.id, "company": subs.get(i.subcontractor_id, "") if i.subcontractor_id else "",
            "subcontractor_id": i.subcontractor_id, "plate": i.plate or "",
            "kind": i.kind or "other", "sent": i.sent or "", "detail": i.detail or "",
            "source": i.source or "", "first_seen": i.first_seen or "",
            "last_seen": i.last_seen or "", "status": i.status or "open",
            "fixed_at": i.fixed_at.strftime("%Y-%m-%d %H:%M") if i.fixed_at else "",
            "fixed_by": i.fixed_by or "", "fixed_note": i.fixed_note or "",
            "created_by": i.created_by or "",
            "created_at": i.created_at.strftime("%Y-%m-%d %H:%M") if i.created_at else ""}


def _apply(i, d):
    if "subcontractor_id" in d:
        i.subcontractor_id = int(d["subcontractor_id"]) if d.get("subcontractor_id") else None
    for f, n in (("plate", 400), ("sent", 300), ("source", 200)):
        if f in d:
            setattr(i, f, str(d.get(f) or "").strip()[:n])
    if "detail" in d:
        i.detail = str(d.get("detail") or "").strip()
    if "kind" in d:
        k = str(d.get("kind") or "other").strip().lower()
        i.kind = k if k in KINDS else "other"
    for f in ("first_seen", "last_seen"):
        if f in d:
            setattr(i, f, _day(d.get(f)))


@bp.route("/data-issues")
@login_required
def page():
    if not _may_view():
        abort(403)
    return render_template("data_issues.html", may_edit=_may_edit())


@bp.get("/api/data-issues")
@login_required
def list_issues():
    if not _may_view():
        abort(403)
    subs = {s.id: (s.short or s.name) for s in Subcontractor.query.all()}
    rows = DataIssue.query.order_by(DataIssue.created_at.desc(), DataIssue.id.desc()).all()
    # Open first: those are the ones that will cost somebody time.
    rows.sort(key=lambda i: 0 if (i.status or "open") == "open" else 1)
    return jsonify(issues=[_out(i, subs) for i in rows],
                   companies=[{"id": k, "name": v} for k, v in sorted(subs.items(), key=lambda x: x[1])],
                   kinds=list(KINDS), may_edit=_may_edit())


@bp.post("/api/data-issues")
@login_required
def add_issue():
    if not _may_edit():
        return jsonify(error="Only an admin logs data issues."), 403
    d = request.get_json(force=True, silent=True) or {}
    if not (str(d.get("detail") or "").strip() or str(d.get("sent") or "").strip()):
        return jsonify(error="Say what is wrong (detail) or what they sent."), 400
    i = DataIssue(created_by=current_user.username, created_at=datetime.utcnow(), status="open")
    _apply(i, d)
    if not i.first_seen:
        i.first_seen = datetime.utcnow().strftime("%Y-%m-%d")
    if not i.last_seen:
        i.last_seen = i.first_seen
    db.session.add(i)
    db.session.commit()
    subs = {s.id: (s.short or s.name) for s in Subcontractor.query.all()}
    return jsonify(ok=True, issue=_out(i, subs))


@bp.post("/api/data-issues/<int:iid>")
@login_required
def edit_issue(iid):
    if not _may_edit():
        return jsonify(error="Only an admin changes data issues."), 403
    i = db.session.get(DataIssue, iid)
    if i is None:
        abort(404)
    d = request.get_json(force=True, silent=True) or {}
    _apply(i, d)
    if "status" in d:
        st = "fixed" if d.get("status") == "fixed" else "open"
        if st == "fixed" and i.status != "fixed":
            i.fixed_at = datetime.utcnow()
            i.fixed_by = current_user.username
            i.fixed_note = str(d.get("fixed_note") or "").strip()[:300]
        elif st == "open":
            i.fixed_at, i.fixed_by, i.fixed_note = None, "", ""
        i.status = st
    db.session.commit()
    subs = {s.id: (s.short or s.name) for s in Subcontractor.query.all()}
    return jsonify(ok=True, issue=_out(i, subs))
