# -*- coding: utf-8 -*-
"""Actual times are stamped once and never rewritten.

Run: python tests/test_actual_stamps.py   (PYTHONIOENCODING=utf-8 on Windows)

22/09/2026. The Monitor, its shift checks and the Managers page used to
rebuild every visit from every ping on every load. The GPS job now writes each
observed time down once (app/actuals.py) and the pages read it back. These are
the rules that make "permanent" safe.
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
from app import actuals                                           # noqa: E402
from app.models import db, ActualStamp, MineArrival, AnchorSeen  # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(62)
          + ("" if ok else "got %r want %r" % (got, want)))


ROLES = {"xppl": 3, "loading": 4, "border": 5, "ql49": 1, "port": 2}
T0 = datetime(2026, 9, 22, 6, 0)          # the run day's local midnight + 6h
DAY = "2026-09-22"


def visit(role, enter_h, exit_h=None, open_=False, plate="20H01498"):
    e = T0 + timedelta(hours=enter_h)
    x = (T0 + timedelta(hours=exit_h)) if exit_h is not None else e
    return {"plate": plate, "anchor_id": ROLES[role], "enter": e, "exit": x,
            "open": open_}


def stamps():
    return {(s.leg, s.role, s.edge): s.at
            for s in ActualStamp.query.filter_by(day=DAY, key="20H01498").all()}


app = create_app()
with app.app_context():
    print("a truck still at the mine")
    vs = [visit("xppl", 0, 1, open_=True), visit("loading", 0.2, 0.9, open_=True)]
    actuals.stamp_days([DAY], vs, ROLES)
    db.session.commit()
    s = stamps()
    check("arrival at the mine is stamped", s.get(("fh", "xppl", "enter")), T0)
    check("leaving is NOT - it is still inside", ("fh", "xppl", "exit") in s, False)

    print("\nit leaves, and the border sees it; later pings move nothing")
    vs = [visit("xppl", 0, 2), visit("loading", 0.2, 1.5),
          visit("border", 5, 6, open_=True)]
    actuals.stamp_days([DAY], vs, ROLES)
    db.session.commit()
    s = stamps()
    check("leaves mine now stamped, at its real exit",
          s.get(("fh", "xppl", "exit")), T0 + timedelta(hours=2))
    check("at border stamped", s.get(("fh", "border", "enter")), T0 + timedelta(hours=5))
    check("crossing waits for the truck to leave", ("fh", "border", "exit") in s, False)

    print("\na stamp is permanent")
    vs = [visit("xppl", 0.5, 3), visit("border", 5, 7)]
    actuals.stamp_days([DAY], vs, ROLES)
    db.session.commit()
    s = stamps()
    check("arrival at the mine kept, not rewritten to 06:30", s.get(("fh", "xppl", "enter")), T0)
    check("leaving kept, not rewritten to 09:00",
          s.get(("fh", "xppl", "exit")), T0 + timedelta(hours=2))
    check("the blank crossing is filled",
          s.get(("fh", "border", "exit")), T0 + timedelta(hours=7))
    n = ActualStamp.query.count()
    actuals.stamp_days([DAY], vs, ROLES)
    db.session.commit()
    check("running again writes nothing", ActualStamp.query.count(), n)

    print("\nthe run home waits for the port's exit")
    vs = [visit("xppl", 0, 2), visit("border", 5, 7), visit("port", 20, 22, open_=True),
          visit("ql49", 25, 26)]
    actuals.stamp_days([DAY], vs, ROLES)
    db.session.commit()
    s = stamps()
    check("at port stamped", s.get(("fh", "port", "enter")), T0 + timedelta(hours=20))
    check("nothing on the way home while still at the port",
          any(k[0] == "bh" for k in s), False)
    vs[2] = visit("port", 20, 23)
    actuals.stamp_days([DAY], vs, ROLES)
    db.session.commit()
    s = stamps()
    check("leaves port stamped once it has left",
          s.get(("bh", "port", "exit")), T0 + timedelta(hours=23))
    check("QL49 on the way home stamped", s.get(("bh", "ql49", "enter")),
          T0 + timedelta(hours=25))

    print("\nvisits from the loop before the mine do not count")
    vs = [visit("border", -3, -2, plate="20H01399"), visit("xppl", 1, 2, plate="20H01399")]
    actuals.stamp_days([DAY], vs, ROLES)
    db.session.commit()
    got = {(s.leg, s.role, s.edge) for s in
           ActualStamp.query.filter_by(day=DAY, key="20H01399").all()}
    check("a border exit before the mine arrival is not this run's",
          ("fh", "border", "exit") in got, False)

    print("\nmine arrivals and seen Locations")
    actuals.record_arrivals([visit("xppl", 0, 2), visit("xppl", 30, 31)], ROLES)
    actuals.record_arrivals([visit("xppl", 0, 2)], ROLES)
    db.session.commit()
    check("each mine entry recorded once", MineArrival.query.count(), 2)
    check("the mine is now a seen Location",
          db.session.get(AnchorSeen, ROLES["xppl"]) is not None, True)

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
