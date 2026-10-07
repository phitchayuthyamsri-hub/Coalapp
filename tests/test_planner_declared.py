# -*- coding: utf-8 -*-
"""The planner sees what the company declared, without waiting for approval.

Run: python tests/test_planner_declared.py   (PYTHONIOENCODING=utf-8 on Windows)

07/10/2026: "if subcontractor declared truck list, please make planner see the
plan." The planner used to read only Manager-approved rows, so a sheet filed by
noon stayed invisible to planning until the supervisor and the manager had
both acted. Now every declared truck reaches the planner; a truck the manager
denied is the only one kept out. The chain itself is untouched.
"""
import json
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
                        DailyListRow)

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


T = datetime.utcnow() + sr.LOCAL_OFFSET
RUN = (T + timedelta(days=1)).strftime("%Y-%m-%d")      # tomorrow's run day

app = create_app()
with app.app_context():
    sub = Subcontractor.query.filter_by(name="Bac Nam").first() or Subcontractor(name="Bac Nam")
    db.session.add(sub)
    db.session.flush()
    adm = User(username="plan@nt", role="admin")
    adm.set_password("x" * 12)
    db.session.add(adm)
    for p in ("20H01469", "20H01474", "20H01481"):
        db.session.add(Truck(plate=p, status="online"))
    # Declared this morning; nobody in the chain has touched it yet.
    dl = DailyList(list_date=RUN, subcontractor_id=sub.id, state="draft")
    db.session.add(dl)
    db.session.flush()
    for plate, state, hhmm in (("20H01469", "pending", "06:00"),
                               ("20H01474", "applied", "07:30"),
                               ("20H01481", "denied", "08:00")):
        db.session.add(DailyListRow(list_id=dl.id, plate=plate, key=plate, note="BH",
                                    ready=True, state=state, arrive_date=RUN,
                                    arrive_hhmm=hhmm))
    db.session.commit()
    uid = str(adm.id)

c = app.test_client()
with c.session_transaction() as s:
    s["_user_id"] = uid
    s["_fresh"] = True

print("the day picker")
d = c.get("/api/shift/plan-day").get_json()
check("opens on the declared run day", d.get("date"), RUN)
check("...counting the declared trucks, not the denied one", d.get("trucks"), 2)

print("\nthe day the planner builds")
with app.test_request_context():
    rev = json.dumps(sr._revision_data(RUN, None), default=str)
check("a pending truck is in the plan's day", "20H01469" in rev, True)
check("a truck sitting with the manager is too", "20H01474" in rev, True)

print("\nthe week")
wk = json.dumps(c.get("/api/shift/week?start=" + RUN).get_json())
check("the declared trucks are in the week", ("20H01469" in wk, "20H01474" in wk), (True, True))

print("\nwhat stays out")
with app.app_context():
    plates = {r.plate for r in sr._plannable_rows().all()}
    denied = DailyListRow.query.filter_by(plate="20H01481").first()
    check("a denied truck is not plannable", "20H01481" in plates, False)
    check("...and says why", sr._why_not_assigned(denied, RUN), "Denied by the manager")
    check("the chain is untouched: the sheet is still a draft",
          DailyList.query.filter_by(list_date=RUN).first().state, "draft")

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
