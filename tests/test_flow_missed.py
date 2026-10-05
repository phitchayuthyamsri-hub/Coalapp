# -*- coding: utf-8 -*-
"""A run day with no sheet is shown as MISSED, not left off the Process page.

Run: python tests/test_flow_missed.py   (PYTHONIOENCODING=utf-8 on Windows)

05/10/2026: Bac Nam declared 03/10 and 05/10 but never 04/10, and the page
went straight from 05/10 to 03/10 - "a quiet past day earns no card". The one
day the chain broke was the one day nobody could see. Now every company that
has declared before is expected every day from its first sheet on, and a run
day that came without a sheet is a red Missed card naming the company.
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
                        DailyListRow, PlanSnapshot)

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


# Relative to the real clock, because the endpoint reads it.
T = datetime.utcnow() + sr.LOCAL_OFFSET
iso = lambda n: (T + timedelta(days=n)).strftime("%Y-%m-%d")
TODAY, YDAY, FIRST, BEFORE, TOMORROW = iso(0), iso(-1), iso(-2), iso(-3), iso(1)

app = create_app()
with app.app_context():
    # The app seeds the companies; Bac Nam is one of them.
    bn = Subcontractor.query.filter_by(name="Bac Nam").first() or Subcontractor(name="Bac Nam")
    other = Subcontractor(name="Never On Test", short="Never On")
    db.session.add_all([bn, other])
    db.session.flush()
    adm = User(username="boss@nt", role="admin")
    adm.set_password("x" * 12)
    db.session.add(adm)
    db.session.add(Truck(plate="20H01381", status="active"))
    for day in (FIRST, TODAY):
        dl = DailyList(list_date=day, subcontractor_id=bn.id, state="confirmed")
        db.session.add(dl)
        db.session.flush()
        db.session.add(DailyListRow(list_id=dl.id, plate="20H01381", key="20H01381",
                                    note="BH", ready=True, state="approved",
                                    arrive_date=day, arrive_hhmm="06:00"))
        db.session.add(PlanSnapshot(week_start=sr._week_start(day).strftime("%Y-%m-%d"),
                                    day=day, subcontractor_id=None, issued_by="plan@nt",
                                    issued_at=datetime.utcnow(), rows=[], figures=[]))
    # A week-wide plan that covers yesterday on paper.
    db.session.add(PlanSnapshot(week_start=sr._week_start(YDAY).strftime("%Y-%m-%d"),
                                day=None, subcontractor_id=None, issued_by="plan@nt",
                                issued_at=datetime.utcnow(), rows=[], figures=[]))
    db.session.commit()
    uid = str(adm.id)
    bn_name = bn.short or bn.name

c = app.test_client()
with c.session_transaction() as s:
    s["_user_id"] = uid
    s["_fresh"] = True
j = c.get("/api/shift/flow").get_json()
by_day = {d["date"]: d for d in j["days"]}

print("the day with no sheet")
check("yesterday is on the page", YDAY in by_day, True)
e = (by_day.get(YDAY) or {"companies": [{}]})["companies"][0]
check("...as missed", e.get("missed"), True)
check("...naming the company", e.get("company"), bn_name)
st = {s["key"]: s for s in e.get("stages", [])}
check("the subcontractor's step is missed", st.get("declare", {}).get("state"), "missed")
check("...the rest were never reached",
      [st[k]["state"] for k in ("submit", "approve", "plan", "watch")], ["idle"] * 4)
check("the week's plan does not count as a plan for it", st.get("plan", {}).get("state"), "idle")
check("the banner says what it cost", "no plan was issued" in e.get("now", {}).get("note", ""), True)
check("...and it is in the tally", j.get("missed"), [{"date": YDAY, "company": bn_name}])

print("\nthe days around it")
check("a declared day is not missed",
      [x.get("missed", False) for x in by_day[TODAY]["companies"]], [False])
check("before the company's first sheet: no card", BEFORE in by_day, False)
check("a company that never declared is not expected",
      any(x.get("company") == "Never On" for d in j["days"] for x in d["companies"]), False)
t = by_day[TOMORROW]["companies"][0]
check("tomorrow with no sheet is still pending, not missed", t.get("missed", False), False)
check("...at the subcontractor", t["stages"][0]["state"], "waiting")
check("...and now names the company", t.get("company"), bn_name)

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
