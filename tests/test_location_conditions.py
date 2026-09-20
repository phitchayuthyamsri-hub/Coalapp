# -*- coding: utf-8 -*-
"""A Location's working conditions: window, type, bays, loading time.

Run: python tests/test_location_conditions.py

Added 20/09/2026. These describe the PLACE - when it can be used, what is
done there, how many bays, how long the work takes. They are not part of the
geofence's shape, so changing one must NOT write a new AnchorVersion: the
whole point of versioning is that a past ping keeps being judged by the shape
that was in force, and none of this can change that.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

_tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL="sqlite:///" + os.path.join(_tmp, "t.db").replace("\\", "/"),
    SECRET_KEY="test-only-not-a-real-key", COALAPP_ENV="")

from app import create_app                                   # noqa: E402
from app.models import db, Anchor, AnchorVersion, User       # noqa: E402

FAIL = 0
SQUARE = [[16.0, 107.0], [16.0, 107.1], [16.1, 107.1], [16.1, 107.0]]


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(58)
          + ("" if ok else "got %r want %r" % (got, want)))


app = create_app()
with app.app_context():
    db.create_all()
    u = User(username="boss", role="admin", is_admin=True)
    u.set_password("x" * 12)
    db.session.add(u)
    db.session.commit()
    uid = u.id

c = app.test_client()
with c.session_transaction() as s:
    s["_user_id"] = str(uid)
    s["_fresh"] = True

print("a new Location carries its conditions")
r = c.post("/api/anchors", json={
    "name": "XPPL Mine", "polygon": SQUARE,
    "loc_type": "load", "window_open": "6:00", "window_close": "18:30",
    "loading_bays": 4, "loading_time_min": 45})
check("created", r.status_code, 200)
AID = r.get_json()["id"]
a = r.get_json()["anchor"]
check("type", a["loc_type"], "load")
check("window opens, padded to HH:MM", a["window_open"], "06:00")
check("window closes", a["window_close"], "18:30")
check("bays", a["loading_bays"], 4)
check("loading time", a["loading_time_min"], 45)

print("\nthe defaults are honest about not knowing")
r = c.post("/api/anchors", json={"name": "Nothing said", "polygon": SQUARE})
b = r.get_json()["anchor"]
check("no type", b["loc_type"], "")
check("no window", (b["window_open"], b["window_close"]), ("", ""))
check("bays are unknown, not zero", b["loading_bays"], None)
check("loading time is unknown, not zero", b["loading_time_min"], None)

print("\nwhat is refused")
check("a window that is not a clock time",
      c.put("/api/anchors/%d" % AID, json={"window_open": "half six"}).status_code, 400)
check("...an hour that does not exist",
      c.put("/api/anchors/%d" % AID, json={"window_open": "25:00"}).status_code, 400)
check("a type nobody offers",
      c.put("/api/anchors/%d" % AID, json={"loc_type": "teleport"}).status_code, 400)
check("negative bays",
      c.put("/api/anchors/%d" % AID, json={"loading_bays": -1}).status_code, 400)
check("loading time that is not a number",
      c.put("/api/anchors/%d" % AID, json={"loading_time_min": "soon"}).status_code, 400)
with app.app_context():
    a = db.session.get(Anchor, AID)
    check("...and none of it stuck", (a.window_open, a.loc_type, a.loading_bays),
          ("06:00", "load", 4))

print("\na window may run over midnight")
r = c.put("/api/anchors/%d" % AID, json={"window_open": "22:00", "window_close": "06:00"})
check("night shift accepted", r.status_code, 200)
check("...as given", (r.get_json()["anchor"]["window_open"],
                      r.get_json()["anchor"]["window_close"]), ("22:00", "06:00"))

print("\nconditions are not the shape")
with app.app_context():
    before = AnchorVersion.query.filter_by(anchor_id=AID).count()
r = c.put("/api/anchors/%d" % AID, json={
    "loc_type": "load_unload", "loading_bays": 6, "loading_time_min": 90})
check("saved", r.status_code, 200)
check("...and wrote no new version", r.get_json()["versioned"], False)
with app.app_context():
    check("...the version count is untouched",
          AnchorVersion.query.filter_by(anchor_id=AID).count(), before)
check("blanking the window is allowed",
      c.put("/api/anchors/%d" % AID,
            json={"window_open": "", "window_close": ""}).get_json()["anchor"]["window_open"], "")
check("clearing the bays means unknown again",
      c.put("/api/anchors/%d" % AID,
            json={"loading_bays": ""}).get_json()["anchor"]["loading_bays"], None)

print("\nmoving the shape still versions, conditions along for the ride")
r = c.put("/api/anchors/%d" % AID, json={
    "polygon": [[16.2, 107.2], [16.2, 107.3], [16.3, 107.3]], "loading_bays": 2})
check("a moved shape is a new version", r.get_json()["versioned"], True)
check("...and the bays saved too", r.get_json()["anchor"]["loading_bays"], 2)

print("\n  " + ("all pass" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
