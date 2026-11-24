# -*- coding: utf-8 -*-
"""Holes in captured GPS are filled from the provider's route history (24/11/2026).

Run: python tests/test_gps_backfill.py   (PYTHONIOENCODING=utf-8 on Windows)

20C21788 on 20/11: TCT's history has it at the mine 01:10-12:36; the minute pull
captured nothing until 19:41, so the Daily page read "did not come". The history
is asked for over the hole only, stored like any ping (own provider, no
duplicates), the mine arrival recorded, and the same hole not asked about again.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
_tmp = tempfile.mkdtemp()
os.environ.update(DATABASE_URL="sqlite:///" + os.path.join(_tmp, "t.db").replace("\\", "/"),
                  SECRET_KEY="test-only-not-a-real-key", COALAPP_ENV="")

from app import create_app                                 # noqa: E402
from app import gps_backfill as gb, gps_ingest as gi        # noqa: E402
from app.models import db, Anchor, GpsPing, GpsGapFill, MineArrival, Truck   # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64) + ("" if ok else "got %r want %r" % (got, want)))


MINE = [[15.74, 106.68], [15.74, 106.71], [15.77, 106.71], [15.77, 106.68]]
LALAY = (16.3141, 106.9695)
app = create_app()
app.config["_GPS_CFG"] = {"tct2": {"enabled": True, "base_url": "http://x", "username": "u", "password": "p"}}
gi.provider_ready = lambda pcfg, key: True
D = datetime(2026, 11, 20)
calls = []


def fake_trail(pcfg, plate, begin, end):
    """TCT's history for 20/11: at the mine 01:10-12:36, then back toward Lalay."""
    calls.append((plate, begin, end))
    pts, t = [], D + timedelta(hours=1, minutes=10)
    while t <= D + timedelta(hours=12, minutes=36):
        pts.append({"dt": t.strftime("%Y-%m-%d %H:%M:%S"), "lat": 15.755, "lng": 106.695, "speed": 3})
        t += timedelta(minutes=5)
    pts.append({"dt": (D + timedelta(hours=19, minutes=41)).strftime("%Y-%m-%d %H:%M:%S"),
                "lat": LALAY[0], "lng": LALAY[1], "speed": 30})       # the captured fix itself
    pts.append({"dt": "2026-11-20 13:00:00", "lat": 0.0, "lng": 0.0, "speed": 0})   # a glitch
    return [p for p in pts if begin <= datetime.strptime(p["dt"], "%Y-%m-%d %H:%M:%S") <= end], [], False


gb.TRAILS["tct2"] = fake_trail
with app.app_context():
    a = Anchor.query.filter_by(name="XPPL Mine").first() or Anchor(name="XPPL Mine")
    a.polygon, a.role = MINE, "xppl"
    db.session.add(a)
    db.session.add(Truck(plate="20C21788", status="online", gps_provider="TCT2"))
    # Captured: 19/11 evening at Lalay, then nothing until 20/11 19:41.
    for t in (D - timedelta(hours=3), D - timedelta(minutes=30), D + timedelta(hours=19, minutes=41),
              D + timedelta(hours=19, minutes=45)):
        db.session.add(GpsPing(plate="20C21788", dt=t, lat=LALAY[0], lng=LALAY[1], speed=0, status="",
                               source="api:tct2"))
    db.session.commit()
    check("the truck counts as a TCT2 truck", gb.trucks(D - timedelta(days=1)), [("20C21788", "tct2")])
    holes = gb.find_gaps("20C21788", "tct2", D, D + timedelta(hours=23, minutes=59))
    check("one hole: 19/11 23:30 to 20/11 19:41", [(h[1], h[2]) for h in holes][:1],
          [(D - timedelta(minutes=30), D + timedelta(hours=19, minutes=41))])

    out = gb.fill(app, D, until=D + timedelta(hours=20), budget_s=60, log=lambda s: None)
    n = GpsPing.query.filter(GpsPing.plate == "20C21788", GpsPing.dt > D,
                             GpsPing.dt < D + timedelta(hours=19)).count()
    check("the mine hours are stored (01:10-12:35 every 5 min)", n, 138)
    check("...the glitch fix is not", GpsPing.query.filter(GpsPing.lat == 0.0).count(), 0)
    check("...the captured 19:41 fix is not stored twice",
          GpsPing.query.filter(GpsPing.dt == D + timedelta(hours=19, minutes=41)).count(), 1)
    check("...stored as the truck's own provider", {g.source for g in GpsPing.query.all()}, {"api:tct2"})
    check("the history was asked for the hole only", [(c[1], c[2]) for c in calls][:1],
          [(D - timedelta(minutes=30), D + timedelta(hours=19, minutes=41))])
    check("the mine arrival is recorded", [m.at.strftime("%d/%m %H:%M") for m in MineArrival.query.all()],
          ["20/11 01:10"])
    check("the summary says what it did", (out["added"], out["days"], out["stamped"]["mine_arrivals"]),
          (138, ["2026-11-20"], 1))
    rec = GpsGapFill.query.first()
    check("the hole is logged as filled", (rec.plate, rec.got, rec.tries), ("20C21788", 138, 1))

    calls.clear()
    out = gb.fill(app, D, until=D + timedelta(hours=20), budget_s=60, log=lambda s: None)
    check("run again: the filled hole is not asked about again", calls, [])

    # A hole the provider has nothing for is asked again later, a few times, then left.
    gb.TRAILS["tct2"] = lambda pcfg, plate, b, e: (calls.append(1) or [], [], False)
    db.session.add(GpsPing(plate="20C21788", dt=D + timedelta(days=1, hours=8), lat=LALAY[0], lng=LALAY[1],
                           speed=0, status="", source="api:tct2"))
    db.session.commit()
    gb._local_now = lambda: D + timedelta(days=1, hours=9)
    calls.clear()
    gb.fill(app, D + timedelta(hours=19), until=D + timedelta(days=1, hours=9), budget_s=60, log=lambda s: None)
    check("an empty hole is asked once", len(calls), 1)
    gb.fill(app, D + timedelta(hours=19), until=D + timedelta(days=1, hours=9), budget_s=60, log=lambda s: None)
    check("...not again straight away", len(calls), 1)
    for r in GpsGapFill.query.filter(GpsGapFill.got == 0).all():
        r.tried_at = datetime.utcnow() - timedelta(hours=4)
    db.session.commit()
    gb.fill(app, D + timedelta(hours=19), until=D + timedelta(days=1, hours=9), budget_s=60, log=lambda s: None)
    check("...but again after 3 hours (late uploads)", len(calls), 2)

print()
print("ALL PASS" if not FAIL else "%d FAILED" % FAIL)
sys.exit(1 if FAIL else 0)
