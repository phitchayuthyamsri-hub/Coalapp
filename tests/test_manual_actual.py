# -*- coding: utf-8 -*-
"""The monitoring team and admins can type an actual time into a Monitor cell.

Run: python tests/test_manual_actual.py   (PYTHONIOENCODING=utf-8 on Windows)

22/09/2026. Right-click a cell, type the time. It is stored as a stamp with
the person's name, shown with a mark, and the GPS job never writes over
it. Clearing removes only a typed time.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

_tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL="sqlite:///" + os.path.join(_tmp, "t.db").replace("\\", "/"),
    SECRET_KEY="test-only-not-a-real-key", COALAPP_ENV="")

from app import create_app                                        # noqa: E402
from app import actuals                                           # noqa: E402
from app.models import (db, User, Truck, Subcontractor, PlanSnapshot,  # noqa: E402
                        ActualStamp)

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(62)
          + ("" if ok else "got %r want %r" % (got, want)))


DAY = "2026-09-22"
app = create_app()
with app.app_context():
    users = {}
    for name, role in (("mon", "monitor"), ("adm", "admin"), ("sub", "subcontractor")):
        u = User(username=name, role=role, is_admin=(role == "admin"))
        u.set_password("x" * 12)
        db.session.add(u)
        users[role] = u
    sub = Subcontractor.query.first() or Subcontractor(name="Bac Nam")
    db.session.add_all([sub, Truck(plate="20H01397", status="active")])
    db.session.flush()
    t = {"arrive_mine": "2026-09-22T23:00", "load_start": "2026-09-22T23:00",
         "load_end": "2026-09-23T00:00", "arrive_border": "2026-09-23T02:56",
         "cross_border": "2026-09-23T15:00", "ql49_arrive": None, "ql49_in": "2026-09-23T19:00",
         "arrive_port": "2026-09-23T21:56", "unload_start": "2026-09-24T08:00",
         "unload_end": "2026-09-24T09:00", "depart_port": "2026-09-24T09:00", "back": "2026-09-24T16:00"}
    db.session.add(PlanSnapshot(week_start="2026-09-21", day=DAY, subcontractor_id=None, issued_by="t",
                                rows=[{"plate": "20H01397", "sub": "Bac Nam", "sub_id": sub.id, "day": DAY,
                                       "loop": 1, "from_plan": False, "route": "hue", "cycle_hours": 41,
                                       "route_name": "", "total_wait": 0, "waits": {}, "t": t}], figures=[]))
    db.session.commit()
    ids = {r: str(u.id) for r, u in users.items()}


def client(role):
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = ids[role]
        s["_fresh"] = True
    return c


def cell(c, leg, key):
    r = [x for x in c.get("/api/shift/track?date=" + DAY).get_json()["rows"] if x["plate"] == "20H01397"][0]
    return [x for x in r[leg] if x["key"] == key][0]


mon = client("monitor")
print("who may")
r = client("subcontractor").post("/api/shift/track/actual", json={"date": DAY, "plate": "20H01397", "leg": "fh", "cell": "mine", "at": "2026-09-22T22:14"})
check("a subcontractor may not", r.status_code, 403)
check("the page is told who may", client("subcontractor").get("/api/shift/track?date=" + DAY).get_json()["may_edit_actual"], False)
check("...and that the monitor may", mon.get("/api/shift/track?date=" + DAY).get_json()["may_edit_actual"], True)

print("\ntyping a time")
r = mon.post("/api/shift/track/actual", json={"date": DAY, "plate": "20H01397", "leg": "fh", "cell": "border", "at": "2026-09-23T03:10"})
check("the monitor enters At border 03:10", r.status_code, 200)
c = cell(mon, "fh", "border")
check("the cell shows it", c["actual"], "2026-09-23T03:10")
check("...marked as typed by mon", c["by"], "mon")
check("...14 min late against the 02:56 plan", c["delay"], 14)

print("\nthe GPS job leaves it alone")
with app.app_context():
    roles = {"xppl": 3, "loading": 4, "border": 5, "ql49": 1, "port": 2}
    T = datetime(2026, 9, 22, 23, 0)
    vis = lambda role, h, h2: {"plate": "20H01397", "anchor_id": roles[role], "enter": T + timedelta(hours=h),
                              "exit": T + timedelta(hours=h2), "open": False}
    n = actuals.stamp_days([DAY], [vis("xppl", 0, 1), vis("border", 3, 4)], roles)
    db.session.commit()
    check("the job stamps what is blank (the mine)", n >= 1, True)
    s = ActualStamp.query.filter_by(day=DAY, key="20H01397", role="border", edge="enter").first()
    check("...but not over the typed border time", (s.at, s.by), (datetime(2026, 9, 23, 3, 10), "mon"))

print("\noverriding and clearing")
r = client("admin").post("/api/shift/track/actual", json={"date": DAY, "plate": "20H01397", "leg": "fh", "cell": "mine", "at": "2026-09-22T22:40"})
check("an admin may write over a GPS time", (r.status_code, cell(mon, "fh", "mine")["actual"]), (200, "2026-09-22T22:40"))
check("...named", cell(mon, "fh", "mine")["by"], "adm")
r = mon.post("/api/shift/track/actual", json={"date": DAY, "plate": "20H01397", "leg": "fh", "cell": "border", "at": ""})
check("blank clears a typed time", (r.status_code, cell(mon, "fh", "border")["actual"]), (200, None))

print("\nthe cell no zone marks")
r = mon.post("/api/shift/track/actual", json={"date": DAY, "plate": "20H01397", "leg": "fh", "cell": "unload", "at": "2026-09-24T08:30"})
check("Unloads takes a typed time", (r.status_code, cell(mon, "fh", "unload")["actual"]), (200, "2026-09-24T08:30"))
r = mon.post("/api/shift/track/actual", json={"date": DAY, "plate": "20H01397", "leg": "fh", "cell": "border", "at": "3pm"})
check("nonsense is refused", r.status_code, 400)

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
