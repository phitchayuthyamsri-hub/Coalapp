# -*- coding: utf-8 -*-
"""The GPS hint is stamped when the company first declares the day, and stays.

Run: python tests/test_hint_stamp.py   (PYTHONIOENCODING=utf-8 on Windows)

08/10/2026: "Can you make GPS hint to stamp the moment sub declare? If
uploaded at 10 am, hint should use the location at 10 am and it stays there"
- and a corrected sheet later does not move it ("no change means the
hinting"). It also took 4-8 s per page open to recompute; a stamped hint is
read back, not rebuilt.
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
from app import shift_routes as sr                                # noqa: E402
from app.models import (db, User, Truck, Subcontractor, DailyList,  # noqa: E402
                        GpsPing)

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


NOW = datetime.utcnow() + sr.LOCAL_OFFSET                  # pings are local time
RUN = (NOW + timedelta(days=1)).strftime("%Y-%m-%d")       # declared for tomorrow

app = create_app()
with app.app_context():
    sub = Subcontractor.query.filter_by(name="Bac Nam").first() or Subcontractor(name="Bac Nam")
    db.session.add(sub)
    db.session.flush()
    u = User(username="huytrv@bacnam", role="subcontractor")
    u.set_password("x" * 12)
    u.subcontractor_id = sub.id
    db.session.add(u)
    db.session.add(Truck(plate="20H01469", status="online", gps_provider="Viettel"))
    # Where the truck is at "10:00": somewhere on the road.
    db.session.add(GpsPing(plate="20H01469", dt=NOW - timedelta(minutes=5),
                           lat=16.40, lng=107.10, speed=40, status="moving",
                           source="api:viettel"))
    db.session.commit()
    uid, SID = str(u.id), sub.id

c = app.test_client()
with c.session_transaction() as s:
    s["_user_id"] = uid
    s["_fresh"] = True


def save(status):
    return c.post("/api/shift/list", json={"date": RUN, "subcontractor_id": SID, "rows": [
        {"plate": "20H01469", "activity": status, "arrive_date": RUN, "arrive": "08:00"}]})


def hint():
    return c.get("/api/shift/suggest?date=%s&subcontractor_id=%d" % (RUN, SID)).get_json()


print("before the day is declared")
h0 = hint()
check("the hint is live", h0.get("stamped"), False)

print("\nthe first declaration")
r = save("BH")
check("the save goes through", r.status_code, 200)
with app.app_context():
    dl = DailyList.query.filter_by(list_date=RUN, subcontractor_id=SID).first()
    first_at, first = dl.hint_at, dl.hint
check("the hint is stamped", first_at is not None, True)
check("...by whoever declared", hint().get("stamped_by"), "huytrv@bacnam")
h1 = hint()
check("the page now reads the stamp", h1.get("stamped"), True)
check("...with the moment it was taken, local time",
      h1.get("stamped_at"), sr._local(first_at).strftime("%Y-%m-%d %H:%M"))
seen1 = [x.get("seen_at") for x in h1.get("rows", []) if x.get("plate") == "20H01469"]
check("...and the position as it was then", seen1, [(NOW - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M")])

print("\nlater: the truck moves and the sheet is saved again")
with app.app_context():
    db.session.add(GpsPing(plate="20H01469", dt=NOW, lat=16.53, lng=107.43, speed=0,
                           status="park", source="api:viettel"))
    db.session.commit()
r = save("FH")
check("the corrected sheet saves", r.status_code, 200)
with app.app_context():
    dl = DailyList.query.filter_by(list_date=RUN, subcontractor_id=SID).first()
    check("the stamp time does not move", dl.hint_at, first_at)
    check("...nor what it says", dl.hint, first)
h2 = hint()
check("the page shows the same hint as before", h2.get("rows"), h1.get("rows"))

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
