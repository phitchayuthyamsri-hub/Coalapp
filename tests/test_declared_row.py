# -*- coding: utf-8 -*-
"""A row's `note` is the declared status, and nothing stands in for it.

Run: python tests/test_declared_row.py   (PYTHONIOENCODING=utf-8 on Windows)

`note` is read as "what this truck is doing" in four places: the Status column
on the supervisor's board, the manager's approval card, the leg the GPS check
compares against, and the fleet-gap test that decides whether a truck has been
answered for at all. It used to fall back to the remark when Status was blank,
so a truck with no status looked answered in all four - including the one that
was supposed to catch it.

That is how Bac Nam's 19/09 sheet put seventeen trucks into the day with the
sentence "Mo het than, xe duoc dieu ve chay than tu Ango di Chan May" sitting
in the Status column, every one of them counted as running.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

_tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL="sqlite:///" + os.path.join(_tmp, "t.db").replace("\\", "/"),
    SECRET_KEY="test-only-not-a-real-key", COALAPP_ENV="")

from app import create_app                      # noqa: E402
from app.models import db, DailyList, Truck     # noqa: E402
from app import shift_routes as sr              # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(58)
          + ("" if ok else "got %r want %r" % (got, want)))


REMARK = "Mo het than, xe duoc dieu ve chay than tu Ango di Chan May"
app = create_app()

with app.app_context():
    print("the remark never stands in for the status")
    r, runs = sr._declared_row(
        {"plate": "20H01381", "activity": "", "remark": REMARK,
         "location": "Ango Yard", "status": "Empty"}, 1, "pending")
    check("a blank Status leaves the declared status blank", r.note, "")
    check("...and the remark is still kept, word for word", r.remark, REMARK)
    check("...in its own column, not the status one", r.remark == r.note, False)

    r, runs = sr._declared_row(
        {"plate": "20H01378", "activity": "FH", "remark": "loaded at the mine"},
        1, "pending")
    check("a declared leg is the status", r.note, "FH")
    check("...and its remark stays separate", r.remark, "loaded at the mine")
    check("...and it counts as running", runs, True)

    r, runs = sr._declared_row(
        {"plate": "20H00789", "activity": "Maintenance", "remark": "18,000 km"},
        1, "pending")
    check("a reason is the status too", r.note, "Maintenance")
    check("...and it does NOT count as running", runs, False)
    check("...and the reason column carries their own words", r.reason, "Maintenance")

    # The supervisor's board sends ticks and timings only. A save that does not
    # mention the status must not erase it - that bug once wiped 58 declared
    # statuses because somebody ticked a box.
    print("\na save keeps what it was not told about")
    prior, _ = sr._declared_row({"plate": "20H01378", "activity": "FH"}, 1, "pending")
    again, _ = sr._declared_row({"plate": "20H01378", "ready": True}, 1, "pending",
                                prior=prior)
    check("a ticks-only save keeps the declared status", again.note, "FH")
    prior2, _ = sr._declared_row(
        {"plate": "20H01381", "activity": "", "remark": REMARK}, 1, "pending")
    again2, _ = sr._declared_row({"plate": "20H01381", "ready": True}, 1, "pending",
                                 prior=prior2)
    check("...and a blank one stays blank, not the remark", again2.note, "")

    # The gap check is what holds the supervisor's submit. With the fallback it
    # read the remark and passed the truck.
    print("\nthe fleet-gap check sees an unanswered truck")
    db.session.add(Truck(plate="20H01381", status="active"))
    db.session.add(Truck(plate="20H01378", status="active"))
    db.session.commit()
    dl = DailyList(list_date="2026-09-19", subcontractor_id=None, state="draft")
    db.session.add(dl)
    db.session.flush()
    for plate, act in (("20H01381", ""), ("20H01378", "FH")):
        row, _ = sr._declared_row({"plate": plate, "activity": act, "remark": REMARK},
                                  dl.id, "pending")
        db.session.add(row)
    db.session.commit()
    gaps = sr._fleet_gaps(dl, None)
    check("a truck with no status is an unanswered truck", "20H01381" in gaps, True)
    check("...and one with a status is not", "20H01378" in gaps, False)

print("\n  %d FAILING" % FAIL if FAIL else "\n  all pass")
sys.exit(1 if FAIL else 0)
