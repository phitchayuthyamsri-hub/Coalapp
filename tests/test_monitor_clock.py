# -*- coding: utf-8 -*-
"""The Monitor shows a stamped time as it happened, on the local clock.

Run: python tests/test_monitor_clock.py   (PYTHONIOENCODING=utf-8 on Windows)

22/09/2026, 20H01397: stamped at the mine at 22:14, and the Monitor showed
"23/09 05:14" - seven hours on, the UTC-to-local shift applied to a time
that was already local (GPS positions are stored on the UTC+7 clock). The
delay against the plan was seven hours wrong with it.
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
from app import shift_routes as sr                                # noqa: E402
from app.models import (db, User, Truck, Subcontractor, PlanSnapshot,  # noqa: E402
                        ActualStamp, MineArrival, Shift, ShiftCheck)

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
    u = User(username="mon", role="monitor")
    u.set_password("x" * 12)
    m = User(username="mgr", role="manager")
    m.set_password("x" * 12)
    sub = Subcontractor.query.first() or Subcontractor(name="Bac Nam")
    db.session.add_all([u, m, sub, Truck(plate="20H01397", status="active")])
    db.session.flush()
    row = {"plate": "20H01397", "sub": "Bac Nam", "sub_id": sub.id, "day": DAY, "loop": 1,
           "from_plan": False, "route": "hue", "cycle_hours": 34.0, "route_name": "",
           "total_wait": 0, "waits": {},
           "t": {"arrive_mine": "2026-09-22T23:00", "load_start": "2026-09-22T23:00",
                 "load_end": "2026-09-23T00:00", "arrive_border": "2026-09-23T02:56",
                 "cross_border": "2026-09-23T15:00", "ql49_arrive": None, "ql49_in": None,
                 "arrive_port": None, "unload_start": None, "unload_end": None,
                 "depart_port": None, "back": "2026-09-24T09:00"}}
    db.session.add(PlanSnapshot(week_start="2026-09-21", day=DAY, subcontractor_id=None,
                                issued_by="t", rows=[row], figures=[]))
    # Stamped at the mine at 22:14 local, 46 minutes before the plan's 23:00.
    at = datetime(2026, 9, 22, 22, 14)
    db.session.add(ActualStamp(day=DAY, key="20H01397", leg="fh", role="xppl", edge="enter", at=at))
    db.session.add(MineArrival(key="20H01397", at=at))
    db.session.commit()
    uid, mid = str(u.id), str(m.id)

c = app.test_client()
with c.session_transaction() as s:
    s["_user_id"] = uid
    s["_fresh"] = True
print("the Monitor table")
r = [x for x in c.get("/api/shift/track?date=" + DAY).get_json()["rows"] if x["plate"] == "20H01397"][0]
check("At mine actual reads 22:14, as stamped", r["fh"][0]["actual"], "2026-09-22T22:14")
check("...46 minutes early against the 23:00 plan", r["fh"][0]["delay"], -46)
check("last seen says the same", r["last_seen"]["at"], "2026-09-22T22:14")

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
