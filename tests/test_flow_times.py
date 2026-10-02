# -*- coding: utf-8 -*-
"""The Process card says when each desk actually did its part.

Run: python tests/test_flow_times.py   (PYTHONIOENCODING=utf-8 on Windows)

02/10/2026, "want to know which time each team submit". The card showed each
desk's window - when the work was DUE - and nothing about when it happened.
Now a stage that was done carries the time, who did it, and how late it was
against its window. Local time (UTC+7), like every time a person reads.
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
from app.models import (db, User, Truck, Subcontractor, DailyList,  # noqa: E402
                        DailyListRow, ActivityEvent, PlanSnapshot)

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


DAY = "2026-10-03"          # the run day; every desk works the day before
U = lambda h, m: datetime(2026, 10, 2, h, m)       # stored UTC; local is +7

app = create_app()
with app.app_context():
    sub = Subcontractor.query.first() or Subcontractor(name="Bac Nam")
    db.session.add(sub)
    db.session.flush()
    for name, role, sid in (("khanh@bacnam", "subcontractor", sub.id), ("anh@nt", "supervisor", None),
                            ("tuan@nt", "manager", None), ("plan@nt", "planner", None)):
        u = User(username=name, role=role)
        u.set_password("x" * 12)
        u.subcontractor_id = sid
        db.session.add(u)
    db.session.add(Truck(plate="20H01381", status="active"))
    dl = DailyList(list_date=DAY, subcontractor_id=sub.id, state="confirmed",
                   submitted_by="anh@nt", submitted_at=U(6, 40),          # 13:40 local
                   confirmed_by="tuan@nt", confirmed_at=U(8, 25))         # 15:25 local
    db.session.add(dl)
    db.session.flush()
    db.session.add(DailyListRow(list_id=dl.id, plate="20H01381", key="20H01381", note="BH",
                                ready=True, state="approved", arrive_date=DAY, arrive_hhmm="06:00"))
    ev = lambda who, action, detail, at: db.session.add(
        ActivityEvent(username=who, action=action, detail=detail, ts=at))
    ev("khanh@bacnam", "upload", "Readiness sheet for 03/10/2026 — 1 truck(s) filled, 0 replaced", U(2, 10))
    ev("khanh@bacnam", "edit", "Saved the declaration for 03/10/2026 — 1 truck(s)", U(4, 35))
    # The supervisor's board saves the same sheet and writes the same line.
    ev("anh@nt", "edit", "Saved the declaration for 03/10/2026 — 1 truck(s)", U(6, 39))
    # Another day's sheet, filed the same morning.
    ev("khanh@bacnam", "edit", "Saved the declaration for 04/10/2026 — 1 truck(s)", U(5, 0))
    db.session.add(PlanSnapshot(week_start="2026-09-28", day=DAY, subcontractor_id=None,
                                issued_by="plan@nt", issued_at=U(9, 5), rows=[], figures=[]))
    db.session.commit()

    with app.test_request_context():
        e = sr._flow_entry(DAY, dl, {sub.id: "Bac Nam"})
    st = {s["key"]: s for s in e["stages"]}

    print("the company")
    check("declared: its own last save, local time", st["declare"].get("at"), "2026-10-02 11:35")
    check("...by the person who saved it", st["declare"].get("by"), "khanh@bacnam")
    check("...the first filing is kept too", st["declare"].get("first_at"), "2026-10-02 09:10")
    check("...inside the 08:00-12:00 window", st["declare"].get("late_min"), 0)

    print("\nthe supervisor")
    check("submitted 13:40", (st["submit"].get("at"), st["submit"].get("by")), ("2026-10-02 13:40", "anh@nt"))
    check("...inside the 12:00-14:00 window", st["submit"].get("late_min"), 0)

    print("\nthe manager")
    check("approved 15:25", (st["approve"].get("at"), st["approve"].get("by")), ("2026-10-02 15:25", "tuan@nt"))
    check("...25 minutes after the 15:00 window closed", st["approve"].get("late_min"), 25)

    print("\nthe planner")
    check("issued 16:05", (st["plan"].get("at"), st["plan"].get("by")), ("2026-10-02 16:05", "plan@nt"))
    check("...inside the 15:30-16:30 window", st["plan"].get("late_min"), 0)
    check("the note no longer repeats the time", st["plan"]["note"], "plan issued by plan@nt")

    print("\nthe monitor, and a desk that has not acted")
    check("the monitor submits nothing, so it carries no time", "at" in st["watch"], False)
    dl.submitted_at, dl.confirmed_at = None, None
    DailyListRow.query.update({"state": "pending"})
    PlanSnapshot.query.delete()
    db.session.commit()
    with app.test_request_context():
        e = sr._flow_entry(DAY, dl, {sub.id: "Bac Nam"})
    st = {s["key"]: s for s in e["stages"]}
    check("nothing submitted: no time on the supervisor", "at" in st["submit"], False)
    check("...but the company's time still stands", st["declare"].get("at"), "2026-10-02 11:35")

    print("\na sheet put in for the company")
    ActivityEvent.query.filter_by(username="khanh@bacnam").delete()
    ev("anh@nt", "upload", "Readiness sheet for 03/10/2026 — 1 truck(s) filled, 0 replaced", U(3, 0))
    db.session.commit()
    with app.test_request_context():
        e = sr._flow_entry(DAY, dl, {sub.id: "Bac Nam"})
    st = {s["key"]: s for s in e["stages"]}
    check("the upload is the time, under the name that did it",
          (st["declare"].get("at"), st["declare"].get("by")), ("2026-10-02 10:00", "anh@nt"))

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
