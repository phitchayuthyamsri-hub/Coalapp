# -*- coding: utf-8 -*-
"""A day nobody can run must not read as a day somebody forgot.

Run: python tests/test_flow_stages.py   (PYTHONIOENCODING=utf-8 on Windows)

When every truck is answered and every answer is a reason it is NOT running,
there is nothing to tick - so Submit rightly refuses, nothing reaches the
manager, and the list stays a draft for ever. Read literally that came out as
"nothing sent to the manager yet", which is word for word what a supervisor who
has not looked at the sheet gets. Two very different days, one sentence.
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

from app import create_app                                  # noqa: E402
from app.models import db, Truck, DailyList, DailyListRow    # noqa: E402
from app import shift_routes as sr                           # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(58)
          + ("" if ok else "got %r want %r" % (got, want)))


DAY = "2026-09-20"
FLEET = ("20H01381", "20H01385", "20H01393")
app = create_app()


def entry(statuses, tick=None, decide=None):
    """Build a day with these declared statuses and read its flow card."""
    with app.app_context():
        DailyListRow.query.delete()
        DailyList.query.delete()
        Truck.query.delete()
        db.session.commit()
        for p in FLEET:
            db.session.add(Truck(plate=p, status="active"))
        dl = DailyList(list_date=DAY, subcontractor_id=None, state="draft")
        db.session.add(dl)
        db.session.flush()
        for plate, st in statuses.items():
            row, _ = sr._declared_row({"plate": plate, "activity": st,
                                       "remark": "company's own words"},
                                      dl.id, "pending")
            if tick and plate in tick:
                row.state = tick[plate]
            if decide and plate in decide:
                row.state = decide[plate]
            db.session.add(row)
        db.session.commit()
        sr._restate(dl)
        db.session.commit()
        return sr._flow_entry(DAY, dl, {})


def stage(e, key):
    return next(s for s in e["stages"] if s["key"] == key)


ALL_DOWN = {"20H01381": "Not available", "20H01385": "Maintenance",
            "20H01393": "Breakdown"}

print("every truck declared down")
e = entry(ALL_DOWN)
sup, man = stage(e, "submit"), stage(e, "approve")
check("the supervisor's stage is done", sup["state"], "done")
check("...and says why", sup["note"], "no trucks available today, 3 declared down")
check("...not 'nothing sent to the manager yet'",
      "nothing sent" in sup["note"], False)
check("the manager has nothing to approve", man["note"], "nothing to approve")
check("...and is not left waiting", man["state"], "done")
check("the declaration itself still reads as complete",
      stage(e, "declare")["note"], "3 trucks declared")
check("the card is not stuck on anybody", e["now"]["who"], "")
check("...and names the reason", e["now"]["note"], "no trucks available today")
check("nothing is marked overdue", [s for s in e["stages"] if s.get("overdue")], [])

print("\na supervisor who simply has not looked yet")
e = entry({"20H01381": "FH", "20H01385": "BH", "20H01393": "Maintenance"})
sup = stage(e, "submit")
check("still says nothing was sent", sup["note"], "nothing sent to the manager yet")
check("...and the chain is stuck on the supervisor", e["now"]["who"], "Supervisor")

print("\na truck with no status at all is a GAP, not an empty day")
e = entry({"20H01381": "", "20H01385": "Maintenance", "20H01393": "Breakdown"})
check("the declaration is unfinished", stage(e, "declare")["state"], "doing")
check("...and the supervisor is not told the day is closed",
      stage(e, "submit")["note"], "nothing sent to the manager yet")

print("\none runnable truck is not an empty day")
e = entry({"20H01381": "FH", "20H01385": "Maintenance", "20H01393": "Breakdown"})
check("the day is still the supervisor's to send",
      stage(e, "submit")["note"], "nothing sent to the manager yet")

print("\nand a day that really did go through is untouched")
e = entry({"20H01381": "FH", "20H01385": "BH", "20H01393": "Maintenance"},
          tick={"20H01381": "applied", "20H01385": "applied"})
check("the supervisor's stage reports what was sent",
      stage(e, "submit")["note"].startswith("2 sent"), True)
check("...and the manager is waiting", stage(e, "approve")["state"], "waiting")
check("...on the right number", stage(e, "approve")["note"],
      "2 truck(s) awaiting approval")

print("\n  %d FAILING" % FAIL if FAIL else "\n  all pass")
sys.exit(1 if FAIL else 0)
