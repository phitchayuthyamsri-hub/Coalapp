# -*- coding: utf-8 -*-
"""Monitor: a cycle's actuals begin at the mine and are walked forward.

Run: python tests/test_monitor_match.py   (PYTHONIOENCODING=utf-8 on Windows)

On 18/09/2026 the Monitor showed truck 20H01397 at QL49 at 03:45 and the port
at 14:07 - 39 hours "early" against a plan whose mine arrival was 13:00 and
had not happened yet. Those were the loop it had just finished. A place
cannot be reached before the place before it, so the matcher now finds the
mine first and only looks past it.
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

from app import create_app                      # noqa: E402
from app import shift_routes as sr              # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(62)
          + ("" if ok else "got %r want %r" % (got, want)))


create_app()                                     # shift_routes needs the app once

ROLES = {"xppl": 1, "border": 2, "ql49": 3, "port": 4}
D = datetime(2026, 9, 18)


def at(h, m=0, day=0):
    return D + timedelta(days=day, hours=h, minutes=m)


def visit(role, enter, exit_=None):
    return {"plate": "20H01397", "anchor_id": ROLES[role], "enter": enter,
            "exit": exit_ or (enter + timedelta(minutes=20))}


def when(m, leg, role):
    v = m.get((leg, role))
    return v["enter"].strftime("%d %H:%M") if v else None


print("the row from the screenshot: last loop's tail, this loop's mine not yet")
# 03:45 QL49 and 14:07 port are the PREVIOUS loop ending. Plan mine 13:00 today.
vs = [visit("ql49", at(3, 45)), visit("port", at(14, 7))]
m = sr._match_cycle(vs, ROLES)
check("no mine visit means no actuals at all", m, {})
check("...so QL49 is not read as 39 hours early", when(m, "fh", "ql49"), None)
check("...nor the port", when(m, "fh", "port"), None)

print("\nthe same truck once it reaches the mine")
vs = [visit("ql49", at(3, 45)), visit("port", at(14, 7)),
      visit("xppl", at(15, 10)),                       # this cycle starts here
      visit("border", at(19, 30)), visit("ql49", at(21, 0)),
      visit("port", at(23, 40), at(1, 15, day=1))]
m = sr._match_cycle(vs, ROLES)
check("the mine anchors the cycle", when(m, "fh", "xppl"), "18 15:10")
check("border is the one AFTER the mine", when(m, "fh", "border"), "18 19:30")
check("QL49 is the one after the border, not the 03:45 one", when(m, "fh", "ql49"), "18 21:00")
check("the port is the one after the mine, not the 14:07 one", when(m, "fh", "port"), "18 23:40")
check("the run home starts at that port", when(m, "bh", "port"), "18 23:40")

print("\nplaces cannot be reached out of order")
# Mine seen, border NOT seen (blind), QL49 seen, port seen, then border seen on
# the way home. Border must not borrow the homeward visit for the loaded run.
vs = [visit("xppl", at(15, 10)), visit("ql49", at(21, 0)),
      visit("port", at(23, 40), at(1, 15, day=1)),
      visit("border", at(6, 0, day=1)), visit("xppl", at(11, 0, day=1))]
m = sr._match_cycle(vs, ROLES)
check("an unseen stop is left empty, not guessed", when(m, "fh", "border"), None)
check("...and the later stops still match", when(m, "fh", "ql49"), "18 21:00")
check("the homeward border is the run home's", when(m, "bh", "border"), "19 06:00")
check("...and the mine at the end is the run home's", when(m, "bh", "xppl"), "19 11:00")
check("...not this cycle's start", when(m, "fh", "xppl"), "18 15:10")

print("\nno port yet: the loaded run is still under way")
vs = [visit("xppl", at(15, 10)), visit("border", at(19, 30))]
m = sr._match_cycle(vs, ROLES)
check("mine and border are matched", (when(m, "fh", "xppl"), when(m, "fh", "border")), ("18 15:10", "18 19:30"))
check("nothing homeward is invented", [k for k in m if k[0] == "bh"], [])

print("\na second visit to the mine before leaving does not restart the cycle")
vs = [visit("xppl", at(15, 10)), visit("xppl", at(16, 0)),
      visit("border", at(19, 30)), visit("port", at(23, 40))]
m = sr._match_cycle(vs, ROLES)
check("the first mine visit is the anchor", when(m, "fh", "xppl"), "18 15:10")
check("...and the rest still follow", when(m, "fh", "port"), "18 23:40")

print("\nthe row is rendered with those picks")
# pick() uses the edge: the run home leaves the port at its EXIT.
vs = [visit("xppl", at(15, 10)), visit("port", at(23, 40), at(1, 15, day=1))]
m = sr._match_cycle(vs, ROLES)
check("port exit is the homeward time", m[("bh", "port")]["exit"].strftime("%d %H:%M"), "19 01:15")

print("\n  %d FAILING" % FAIL if FAIL else "\n  all pass")
sys.exit(1 if FAIL else 0)
