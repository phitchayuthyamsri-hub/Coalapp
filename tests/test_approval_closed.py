# -*- coding: utf-8 -*-
"""A day's trucks cannot be approved once the approval day has passed.

Run: python tests/test_approval_closed.py   (PYTHONIOENCODING=utf-8 on Windows)

22/10/2026: the 22/10 sheet was still waiting for the manager on 22/10 itself
- the approval day (21/10) long gone. "From now on, please denied approval if
it's already pass the date." Approval belongs to the day before the run day;
from the run day on, the manager's Approve is refused, the Managers page says
the approval is closed, and Process shows the day closed instead of waiting.
The admin can still approve, to put a mistake right.
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
from app.models import db, User, Subcontractor, DailyList, DailyListRow  # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


T = datetime.utcnow() + sr.LOCAL_OFFSET
TODAY, TOMORROW = T.strftime("%Y-%m-%d"), (T + timedelta(days=1)).strftime("%Y-%m-%d")

app = create_app()
ids = {}
with app.app_context():
    bn = Subcontractor.query.filter_by(name="Bac Nam").first() or Subcontractor(name="Bac Nam")
    db.session.add(bn)
    db.session.flush()
    BN = bn.id
    for name, role, adm in (("tuan", "manager", False), ("boss", "admin", True)):
        u = User(username=name, role=role, is_admin=adm)
        u.set_password("x" * 12)
        db.session.add(u)
        db.session.flush()
        ids[name] = str(u.id)
    for day in (TODAY, TOMORROW):
        dl = DailyList(list_date=day, subcontractor_id=BN, state="submitted",
                       submitted_by="anh", submitted_at=datetime.utcnow())
        db.session.add(dl)
        db.session.flush()
        db.session.add(DailyListRow(list_id=dl.id, plate="20H01469", key="20H01469", note="BH",
                                    ready=True, state="applied", arrive_date=day, arrive_hhmm="08:00"))
    db.session.commit()


def client(who):
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = ids[who]
        s["_fresh"] = True
    return c


def state(day):
    with app.app_context():
        return DailyList.query.filter_by(list_date=day).first().state


print("the run day has come: approval is closed")
ap = client("tuan").get("/api/shift/approvals?date=%s&subcontractor_id=%d" % (TODAY, BN)).get_json()
l = (ap.get("lists") or [{}])[0]
check("the Managers page says so", (l.get("approval_closed"), l.get("can_decide")), (True, False))
r = client("tuan").post("/api/shift/list/confirm", json={"date": TODAY, "subcontractor_id": BN})
check("the manager's Approve is refused", (r.status_code, r.get_json().get("code")), (403, "approval_closed"))
check("...with the reason", "had to be approved on" in r.get_json().get("error", ""), True)
check("...and nothing was approved", state(TODAY), "submitted")
with app.test_request_context():
    with app.app_context():
        dl = DailyList.query.filter_by(list_date=TODAY).first()
        e = sr._flow_entry(TODAY, dl, {BN: "Bac Nam"}, today=TODAY)
man = {s["key"]: s for s in e["stages"]}["approve"]
check("Process: the manager's step is closed, not waiting", man["state"], "missed")
check("...and the day reads closed", (e["now"]["who"], e["now"]["closed"]), ("Manager", True))

print("\nthe approval day itself: still open")
ap = client("tuan").get("/api/shift/approvals?date=%s&subcontractor_id=%d" % (TOMORROW, BN)).get_json()
check("Approve offered", (ap["lists"][0]["approval_closed"], ap["lists"][0]["can_decide"]), (False, True))
r = client("tuan").post("/api/shift/list/confirm", json={"date": TOMORROW, "subcontractor_id": BN})
check("...and it goes through", (r.status_code, state(TOMORROW)), (200, "confirmed"))

print("\nthe admin can still put a mistake right")
r = client("boss").post("/api/shift/list/confirm", json={"date": TODAY, "subcontractor_id": BN})
check("a late approval by the admin goes through", (r.status_code, state(TODAY)), (200, "confirmed"))

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
