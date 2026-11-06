# -*- coding: utf-8 -*-
"""A company with trucks in the fleet is on the Process page before its first sheet.

Run: python tests/test_flow_go_live.py   (PYTHONIOENCODING=utf-8 on Windows)

06/11/2026: PTS and BBC had 60 trucks in the fleet since 04/11 but had never
declared, and the page only expected companies that had - so they were not on
it. They are expected from the first run day they are seen with trucks, which
is written down once: it does not slide forward, so a day they then miss is
shown as missed, and the days before they joined are not.
"""
import os
import sys
import tempfile
import json
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

_tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL="sqlite:///" + os.path.join(_tmp, "t.db").replace("\\", "/"),
    SECRET_KEY="test-only-not-a-real-key", COALAPP_ENV="")

from app import create_app                                        # noqa: E402
from app import shift_routes as sr                                # noqa: E402
from app.models import db, User, Truck, Subcontractor, KVStore    # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


T = datetime.utcnow() + sr.LOCAL_OFFSET
iso = lambda n: (T + timedelta(days=n)).strftime("%Y-%m-%d")
TODAY, TOMORROW, YDAY = iso(0), iso(1), iso(-1)

app = create_app()
with app.app_context():
    pts = Subcontractor.query.filter_by(name="PTS").first() or Subcontractor(name="PTS", short="PTS")
    idle = Subcontractor(name="No Trucks Co", short="NoTrucks")
    gone = Subcontractor(name="All Gone Co", short="AllGone")
    db.session.add_all([pts, idle, gone])
    db.session.flush()
    db.session.add_all([Truck(plate="74H01966", status="online", subcontractor_id=pts.id),
                        Truck(plate="11A11111", status="deactivated", subcontractor_id=gone.id)])
    adm = User(username="boss", role="admin")
    adm.set_password("x" * 12)
    db.session.add(adm)
    db.session.commit()
    uid, PTS = str(adm.id), pts.id

c = app.test_client()
with c.session_transaction() as s:
    s["_user_id"] = uid
    s["_fresh"] = True
j = c.get("/api/shift/flow").get_json()
by = {d["date"]: [x.get("company") for x in d["companies"]] for d in j["days"]}
check("the company with trucks is on tomorrow's card", "PTS" in by.get(TOMORROW, []), True)
tm = [x for d in j["days"] if d["date"] == TOMORROW for x in d["companies"] if x.get("company") == "PTS"][0]
check("...waiting at the subcontractor, not missed", (tm.get("missed", False), tm["stages"][0]["state"]), (False, "waiting"))
check("...and not on the days before it joined", "PTS" in by.get(TODAY, []) or "PTS" in by.get(YDAY, []), False)
check("a company with no trucks is not expected", any("NoTrucks" in v for v in by.values()), False)
check("...nor one whose trucks are all deactivated", any("AllGone" in v for v in by.values()), False)
check("no company of ours is marked missed", [m for m in j.get("missed", []) if m["company"]], [])

with app.app_context():
    stored = json.loads(db.session.get(KVStore, sr.GO_LIVE_KEY).value)
check("the go-live day is written down", stored, {str(PTS): TOMORROW})

# A later day: the date stays where it was, so tomorrow - once past - would
# count as missed instead of sliding forward with the calendar.
with app.app_context():
    got = sr._go_live(iso(5))
check("...and does not move when asked again later", got, {PTS: TOMORROW})

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
