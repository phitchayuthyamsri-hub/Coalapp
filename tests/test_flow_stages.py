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


def entry(statuses, tick=None, decide=None, times=None):
    """Build a day with these declared statuses and read its flow card.

    `times` gives a plate its mine arrival as (date, hh:mm). That is what makes
    a truck plannable, and its absence is what makes a day unplannable."""
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
            payload = {"plate": plate, "activity": st,
                       "remark": "company's own words"}
            if times and plate in times:
                payload["arrive_date"], payload["arrive_time"] = times[plate]
            row, _ = sr._declared_row(payload, dl.id, "pending")
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
check("the supervisor's desk had nothing to do - not a tick", sup["state"], "none")
check("...and says why", sup["note"], "no trucks available today, 3 declared down")
check("...not 'nothing sent to the manager yet'",
      "nothing sent" in sup["note"], False)
check("the manager has nothing to approve", man["note"], "nothing to approve - no coal load")
check("...and is not left waiting, nor ticked", man["state"], "none")
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
          tick={"20H01381": "applied", "20H01385": "applied"},
          times={"20H01385": (DAY, "06:00")})
check("the supervisor's stage reports what was sent",
      stage(e, "submit")["note"].startswith("2 sent"), True)
check("...and the manager is waiting", stage(e, "approve")["state"], "waiting")
check("...on the right number", stage(e, "approve")["note"],
      "2 truck(s) awaiting approval")

# ── a sheet nothing can be planned from ────────────────────────────────────
# The planner seeds from trucks arriving at the mine to LOAD. A day of nothing
# but FH has no arrival times at all: those trucks are already loaded and
# running to port, so they are delivering, but none is coming back to start a
# cycle. Before this the chain marched on to the Planner, sat there as
# "20 approved truck(s), no plan issued yet", and went overdue at 16:30.
ALL_FH = {p: "FH" for p in FLEET}

print("\nevery truck FH, no mine arrival time - the 19/09 shape")
e = entry(ALL_FH, tick={p: "applied" for p in FLEET})
plan = stage(e, "plan")
check("the planner is not left waiting - and not ticked", plan["state"], "none")
check("...and says there is nothing to plan",
      plan["note"], "nothing to plan - no truck is due at the mine")
check("...and is never overdue for it", plan.get("overdue"), None)
check("the monitor has nothing to watch", stage(e, "watch")["note"], "nothing to watch")
check("the chain stops at the supervisor - nothing to approve",
      stage(e, "approve")["note"], "nothing to approve - no coal load")
check("...so the manager is a dash, not pending", stage(e, "approve")["state"], "none")
check("...and the day sits on nobody's desk", e["now"]["who"], "")
check("...the supervisor's send is still on the record",
      stage(e, "submit")["note"].startswith("3 sent"), True)

print("\n...and once the manager has approved it")
e = entry(ALL_FH, decide={p: "approved" for p in FLEET})
check("the planner still has nothing to plan",
      stage(e, "plan")["note"], "nothing to plan - no truck is due at the mine")
check("...is not waiting, nor ticked", stage(e, "plan")["state"], "none")
check("...and is not overdue", stage(e, "plan").get("overdue"), None)
check("nobody is holding the day up", e["now"]["who"], "")
check("...and the card says why",
      e["now"]["note"], "nothing to plan - no truck is due at the mine")

print("\na truck due at the mine on ANOTHER day says so")
e = entry(ALL_FH, decide={p: "approved" for p in FLEET},
          times={"20H01381": ("2026-09-22", "06:00")})
check("the note counts the trucks due elsewhere",
      stage(e, "plan")["note"],
      "nothing to plan - no truck is due at the mine, 1 due on another day")

print("\none truck due at the mine IS a plannable day")
e = entry({"20H01381": "BH", "20H01385": "FH", "20H01393": "Maintenance"},
          decide={"20H01381": "approved", "20H01385": "approved"},
          times={"20H01381": (DAY, "06:00")})
plan = stage(e, "plan")
check("the planner is asked for a plan", plan["state"], "waiting")
check("...with the old wording", plan["note"], "2 approved truck(s), no plan issued yet")
check("...and the day waits on the planner", e["now"]["who"], "Planner")
check("the monitor is idle until a plan exists", stage(e, "watch")["note"], "")

print("\nan all-down day is also a day nothing can be planned from")
e = entry(ALL_DOWN)
check("the planner says so too",
      stage(e, "plan")["note"], "nothing to plan - no truck is due at the mine")
check("but the headline names the more specific reason",
      e["now"]["note"], "no trucks available today")

# ── the banner: said once, above the chain ────────────────────────────────
print("\nthe no-coal-load banner")
e = entry(ALL_FH, tick={p: "applied" for p in FLEET})
check("an all-FH day carries the banner", e["no_load"], True)
check("...and says why, and what follows",
      e["no_load_note"],
      "no truck is due at the mine to load, so there is no plan to issue")
check("...and nobody is asked to decide anything", e["now"]["who"], "")
e = entry(ALL_FH, decide={p: "approved" for p in FLEET},
          times={"20H01381": ("2026-09-22", "06:00")})
check("trucks due on another day are counted in it",
      e["no_load_note"],
      "no truck is due at the mine to load - 1 due on another day, so there is no plan to issue")
e = entry(ALL_DOWN)
check("an all-down day carries it too", e["no_load"], True)
check("...with its own reason",
      e["no_load_note"],
      "every truck is declared down (3 of 3), so nothing runs and there is no plan to issue")
check("only the desk that did work is ticked",
      [s2["who"] for s2 in e["stages"] if s2["state"] == "done"], ["Subcontractor"])
e = entry({"20H01381": "BH", "20H01385": "FH", "20H01393": "Maintenance"},
          decide={"20H01381": "approved", "20H01385": "approved"},
          times={"20H01381": (DAY, "06:00")})
check("a plannable day has no banner", e["no_load"], False)
check("...and an empty note", e["no_load_note"], "")

print("\na manager who already approved a no-load day keeps the record")
e = entry(ALL_FH, decide={p: "approved" for p in FLEET})
check("their decision is not erased into a dash", stage(e, "approve")["state"], "done")
check("...and still reads as theirs", stage(e, "approve")["note"], "3 approved, 0 denied")

print("\na BH truck with no arrival time is a no-load day")
e = entry({"20H01381": "BH", "20H01385": "FH", "20H01393": "Maintenance"},
          tick={"20H01381": "applied", "20H01385": "applied"})
check("the banner is up", e["no_load"], True)
check("the chain stops at the supervisor", stage(e, "approve")["state"], "none")
check("...even though two trucks were sent", stage(e, "submit")["note"].startswith("2 sent"), True)

print("\n  %d FAILING" % FAIL if FAIL else "\n  all pass")
sys.exit(1 if FAIL else 0)
