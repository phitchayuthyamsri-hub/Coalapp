# -*- coding: utf-8 -*-
"""A truck is declared the day before it arrives.

Run: python tests/test_same_day.py   (PYTHONIOENCODING=utf-8 on Windows)

22/09/2026, "from tomorrow onward, block truck that arrive in same day". A
declaration row timed for the day it is filed on, or earlier, is refused by
the save and by the upload, by name. Dated: lists filed before the rule are
not touched by it.
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
from app.models import db, User, Subcontractor, Truck             # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(62)
          + ("" if ok else "got %r want %r" % (got, want)))


app = create_app()
with app.app_context():
    u = User(username="sub1", role="subcontractor")
    u.set_password("x" * 12)
    sub = Subcontractor.query.first() or Subcontractor(name="Bac Nam")
    db.session.add_all([u, sub])
    db.session.flush()
    u.subcontractor_id = sub.id
    for p in ("20H01498", "20H01499"):
        db.session.add(Truck(plate=p, status="active"))
    db.session.commit()
    uid, sid = str(u.id), sub.id

today = (datetime.utcnow() + sr.LOCAL_OFFSET).strftime("%Y-%m-%d")
tomorrow = (datetime.utcnow() + sr.LOCAL_OFFSET + timedelta(days=1)).strftime("%Y-%m-%d")
yesterday = (datetime.utcnow() + sr.LOCAL_OFFSET - timedelta(days=1)).strftime("%Y-%m-%d")

print("the rule itself")
sr.SAME_DAY_RULE_FROM = "2000-01-01"
rows = [{"plate": "20H01498", "arrive_date": today},
        {"plate": "20H01499", "arrive_date": tomorrow},
        {"plate": "20H01500", "arrive_date": yesterday},
        {"plate": "20H01501", "arrive_date": ""}]
check("today and earlier are named, tomorrow and blank are not",
      sr._same_day_rows(rows), ["20H01498", "20H01500"])
sr.SAME_DAY_RULE_FROM = "2999-01-01"
check("before the rule's day nothing is refused", sr._same_day_rows(rows), [])
sr.SAME_DAY_RULE_FROM = "2000-01-01"

c = app.test_client()
with c.session_transaction() as s:
    s["_user_id"] = uid
    s["_fresh"] = True

print("\nthe on-screen save")
body = {"date": tomorrow, "subcontractor_id": sid, "rows": [
    {"plate": "20H01498", "status": "BH", "arrive_date": today, "arrive_time": "06:00"},
    {"plate": "20H01499", "status": "BH", "arrive_date": tomorrow, "arrive_time": "06:15"}]}
r = c.post("/api/shift/list", json=body)
j = r.get_json()
check("a truck timed for today is refused", r.status_code, 400)
check("...by name", j.get("plates"), ["20H01498"])
check("...with the code the page reads", j.get("code"), "same_day")
body["rows"][0]["arrive_date"] = tomorrow
r = c.post("/api/shift/list", json=body)
check("timed for tomorrow it saves", r.status_code, 200)
body["rows"][0]["arrive_date"] = ""
body["rows"][0]["status"] = "Breakdown"
r = c.post("/api/shift/list", json=body)
check("a truck not running has no date and is not refused", r.status_code, 200)

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
