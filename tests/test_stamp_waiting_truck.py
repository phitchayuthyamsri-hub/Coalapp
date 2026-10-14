# -*- coding: utf-8 -*-
"""A truck that waits at the mine across days is stamped on the day it ran.

Run: python tests/test_stamp_waiting_truck.py   (PYTHONIOENCODING=utf-8 on Windows)

14/10/2026, 20H01485: entered the mine 10/10 19:50, declared for 11/10 and
again for 12/10, loaded 12/10 12:33, left 13:50, at the border 13/10. Every GPS
time was filed under 11/10 and the 12/10 row - the one the team watches - was
empty, so they typed the times by hand. Each run day only looked at visits
that STARTED inside its window, and this truck's mine stay started before
12/10's.
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
from app import actuals                                           # noqa: E402
from app.models import db, Subcontractor, DailyList, DailyListRow, ActualStamp  # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


D = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M")
ROLES = {"xppl": 1, "loading": 2, "border": 3, "ql49": 4, "port": 5}
P = "20H01485"


def visit(aid, enter, exit_=None):
    return {"plate": P, "anchor_id": aid, "enter": D(enter),
            "exit": D(exit_) if exit_ else None, "open": exit_ is None}


VISITS = [visit(1, "2026-10-10 19:50", "2026-10-12 13:50"),     # at the mine, waiting
          visit(2, "2026-10-12 12:33", "2026-10-12 13:31"),     # loading
          visit(3, "2026-10-13 10:13", "2026-10-13 17:35")]     # border

app = create_app()
with app.app_context():
    sub = Subcontractor.query.filter_by(name="Bac Nam").first() or Subcontractor(name="Bac Nam")
    db.session.add(sub)
    db.session.flush()
    for day in ("2026-10-11", "2026-10-12"):
        dl = DailyList(list_date=day, subcontractor_id=sub.id, state="confirmed")
        db.session.add(dl)
        db.session.flush()
        db.session.add(DailyListRow(list_id=dl.id, plate=P, key=P, note="BH", ready=True,
                                    state="approved", arrive_date=day, arrive_hhmm="12:00"))
    db.session.commit()

    actuals.stamp_days(["2026-10-11", "2026-10-12"], VISITS, ROLES)
    db.session.commit()
    got = {}
    for s in ActualStamp.query.filter_by(key=P).all():
        got.setdefault(s.day, {})[(s.leg, s.role, s.edge)] = s.at.strftime("%d/%m %H:%M")
    d11, d12 = got.get("2026-10-11", {}), got.get("2026-10-12", {})

    print("12/10 - the day it actually ran")
    check("at the mine: the stay it was still in", d12.get(("fh", "xppl", "enter")), "10/10 19:50")
    check("loading", (d12.get(("fh", "loading", "enter")), d12.get(("fh", "loading", "exit"))),
          ("12/10 12:33", "12/10 13:31"))
    check("leaves the mine", d12.get(("fh", "xppl", "exit")), "12/10 13:50")
    check("at the border", d12.get(("fh", "border", "enter")), "13/10 10:13")

    print("\n11/10 - declared, but it waited")
    check("keeps its arrival at the mine", d11.get(("fh", "xppl", "enter")), "10/10 19:50")
    check("...and nothing after it", sorted(k for k in d11 if k != ("fh", "xppl", "enter")), [])

    print("\na truck NOT declared again keeps its run where it was")
    ActualStamp.query.delete()
    DailyListRow.query.filter(DailyListRow.list_id.in_(
        [x.id for x in DailyList.query.filter_by(list_date="2026-10-12").all()])).delete(
        synchronize_session=False)
    db.session.commit()
    actuals.stamp_days(["2026-10-11", "2026-10-12"], VISITS, ROLES)
    db.session.commit()
    days = {s.day for s in ActualStamp.query.filter_by(key=P, role="loading").all()}
    check("the loading stays on 11/10", days, {"2026-10-11"})

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
