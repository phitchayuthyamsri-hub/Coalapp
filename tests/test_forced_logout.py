# -*- coding: utf-8 -*-
"""Signing everyone out, the admin excepted (21/10/2026).

Run: python tests/test_forced_logout.py   (PYTHONIOENCODING=utf-8 on Windows)

A session is a signed cookie: there is nothing on the server to delete. Each
login now carries the moment it was made, and a non-admin session older than
its user's logout_before is ended on its next request.
"""
import os
import sys
import tempfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

_tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL="sqlite:///" + os.path.join(_tmp, "t.db").replace("\\", "/"),
    SECRET_KEY="test-only-not-a-real-key", COALAPP_ENV="")

from app import create_app                                        # noqa: E402
from app.models import db, User                                   # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


app = create_app()
ids = {}
with app.app_context():
    for name, role, adm in (("boss", "admin", True), ("hieu", "subcontractor", False)):
        u = User(username=name, role=role, is_admin=adm)
        u.set_password("pw-" + name + "-12345")
        db.session.add(u)
        db.session.flush()
        ids[name] = u.id
    db.session.commit()


def old_session(who):
    """A session from before login times were kept."""
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = str(ids[who])
        s["_fresh"] = True
    return c


hieu, boss = old_session("hieu"), old_session("boss")
check("before: the subcontractor is signed in", hieu.get("/api/me").status_code, 200)

with app.app_context():
    now = datetime.utcnow()
    for u in User.query.all():
        u.logout_before = now          # the admin too, to show it is skipped
    db.session.commit()

print("after everyone is signed out")
r = hieu.get("/api/me")
check("the subcontractor's API call is refused", r.status_code, 401)
check("...and the session is gone for good", hieu.get("/api/me").status_code, 401)
r = old_session("hieu").get("/tool")
check("a page sends them to the login form",
      (r.status_code, "/login" in (r.headers.get("Location") or "")), (302, True))
check("the admin stays signed in", boss.get("/api/me").status_code, 200)

print("\nlogging in again")
c = app.test_client()
r = c.post("/login", data={"username": "hieu", "password": "pw-hieu-12345"})
check("the login goes through", r.status_code, 302)
check("...and the new session works", c.get("/api/me").status_code, 200)
check("...on later requests too", c.get("/api/me").get_json().get("username"), "hieu")

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
