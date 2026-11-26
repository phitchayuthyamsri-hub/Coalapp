# -*- coding: utf-8 -*-
"""A company login watches its own trucks on the Monitor and the map (16/11/2026).

Run: python tests/test_sub_monitor.py   (PYTHONIOENCODING=utf-8 on Windows)

User: subcontractors may view the monitoring, view only, and only their own
company's trucks. The team's remarks are its own notes and are not shown to
a company. Nothing on the Monitor can be written from a company login (or a
spectator), whatever the page sends.
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
from app.models import (db, User, Truck, Subcontractor, PlanSnapshot,  # noqa: E402
                        MonitorRemark, Anchor, GpsPing)

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


DAY = "2026-11-16"
SQ = [[16.0, 106.0], [16.0, 106.01], [16.01, 106.01], [16.01, 106.0]]
app = create_app()
from app import shift_routes as _sr_pin   # noqa: E402
_sr_pin.SHIFT_MODE_FROM = "2099-01-01"   # one-file sheets; AM / PM files: test_shift_files.py
_sr_pin.FLEET_RULE_FROM = "2099-01-01"   # fleet rule: test_fleet_rule.py
with app.app_context():
    def _sub(name):
        s = Subcontractor.query.filter_by(name=name).first() or Subcontractor(name=name, short=name)
        db.session.add(s)
        return s
    bn, hs = _sub("Bac Nam"), _sub("Hoanh Son")
    db.session.flush()
    users = {}
    for name, role, sid in (("mon", "monitor", None), ("adm", "admin", None), ("bn", "subcontractor", bn.id),
                            ("spec", "spectator", None)):
        u = User(username=name, role=role, is_admin=(role == "admin"), subcontractor_id=sid)
        u.set_password("x" * 12)
        db.session.add(u)
        users[name] = u
    db.session.add_all([Truck(plate="20H01397", status="active", subcontractor_id=bn.id),
                        Truck(plate="38H03034", status="active", subcontractor_id=hs.id)])
    if not Anchor.query.first():
        db.session.add(Anchor(name="XPPL", polygon=SQ))
    t = {"arrive_mine": DAY + "T23:00", "load_start": DAY + "T23:00", "load_end": "2026-11-17T00:00",
         "arrive_border": "2026-11-17T02:56", "cross_border": "2026-11-17T15:00", "ql49_arrive": None,
         "ql49_in": "2026-11-17T19:00", "arrive_port": "2026-11-17T21:56", "unload_start": "2026-11-18T08:00",
         "unload_end": "2026-11-18T09:00", "depart_port": "2026-11-18T09:00", "back": "2026-11-18T16:00"}
    row = lambda plate, sub: {"plate": plate, "sub": sub.name, "sub_id": sub.id, "day": DAY, "loop": 1,
                              "from_plan": False, "route": "hue", "cycle_hours": 41, "route_name": "",
                              "total_wait": 0, "waits": {}, "t": t}
    db.session.add(PlanSnapshot(week_start="2026-11-16", day=DAY, subcontractor_id=None, issued_by="t",
                                rows=[row("20H01397", bn), row("38H03034", hs)], figures=[]))
    for plate in ("20H01397", "38H03034"):
        db.session.add(MonitorRemark(day=DAY, key=plate, text="team note on " + plate, by="mon"))
    now_local = datetime.utcnow() + timedelta(hours=7)
    for plate in ("20H01397", "38H03034"):
        db.session.add(GpsPing(plate=plate, dt=now_local - timedelta(minutes=5), lat=16.005, lng=106.005))
    db.session.commit()
    ids = {k: str(u.id) for k, u in users.items()}


def client(name):
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = ids[name]
        s["_fresh"] = True
    return c


bn = client("bn")
print("\nA company login can open the Monitor and the map")
check("Monitor page opens", bn.get("/monitor").status_code, 200)
check("map page opens", bn.get("/map").status_code, 200)
j = bn.get("/api/shift/track?date=" + DAY).get_json()
check("Monitor rows: its own truck only", sorted(r["plate"] for r in j["rows"]), ["20H01397"])
check("...told it is view-only", (j["read_only"], j["may_edit_actual"]), (True, False))
check("...the team's remarks are not sent, and the column is hidden", (j["remarks"], j["hide_remarks"]), ({}, True))
m = bn.get("/api/shift/map?date=" + DAY).get_json()
check("map: its own truck's position only", sorted(x["plate"] for x in m.get("trucks", [])) + sorted(x["plate"] for x in m.get("unseen", [])), ["20H01397"])

print("\n...and cannot write anything there")
r = bn.post("/api/shift/track/remark", json={"date": DAY, "plate": "20H01397", "text": "hello"})
check("remark refused", r.status_code, 403)
r = bn.post("/api/shift/track/actual", json={"date": DAY, "plate": "20H01397", "leg": "fh", "cell": "mine", "at": DAY + "T22:00"})
check("typed time refused", r.status_code, 403)
r = client("spec").post("/api/shift/track/remark", json={"date": DAY, "plate": "20H01397", "text": "hello"})
check("a spectator cannot write a remark either", r.status_code, 403)
with app.app_context():
    check("...the team's note is unchanged", MonitorRemark.query.filter_by(day=DAY, key="20H01397").first().text, "team note on 20H01397")

print("\nEveryone else as before")
mon = client("mon")
j = mon.get("/api/shift/track?date=" + DAY).get_json()
check("monitoring team sees both companies and the remarks", (len(j["rows"]), len(j["remarks"]), j["read_only"]), (2, 2, False))
check("monitoring team still writes remarks", mon.post("/api/shift/track/remark", json={"date": DAY, "plate": "38H03034", "text": "ok"}).status_code, 200)
m = client("adm").get("/api/shift/map?date=" + DAY).get_json()
check("admin map: every truck", len(m.get("trucks", [])) + len(m.get("unseen", [])), 2)

print("\n" + ("%d FAILED" % FAIL if FAIL else "ALL PASS"))
sys.exit(1 if FAIL else 0)
