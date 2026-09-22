# -*- coding: utf-8 -*-
"""A truck seen inside a zone and nowhere since has been there until now.

Run: python tests/test_open_visit.py

22/09/2026, 20H01397: one ping inside the mine at 22:14, no second ping yet,
and the five-minute dwell threw the visit away - the Monitor said "on the
road" while the truck stood at the mine. An OPEN visit lasts until `now`.
"""
import os
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from app import engine   # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(60)
          + ("" if ok else "got %r want %r" % (got, want)))


ZONE = {"id": 3, "name": "XPPL Mine", "min_dwell_min": 5,
        "polygon": [[15.74, 106.68], [15.74, 106.71], [15.76, 106.71], [15.76, 106.68]]}
T = datetime(2026, 9, 22, 22, 14, 58)
outside = {"plate": "20H01397", "dt": T - timedelta(hours=1), "lat": 15.93, "lng": 106.64, "speed": 37, "status": ""}
inside = {"plate": "20H01397", "dt": T, "lat": 15.7506, "lng": 106.6935, "speed": 6, "status": ""}

v = engine.build_visits([outside, inside], [ZONE])
check("without a clock, one ping inside is not yet a visit", len(v), 0)
v = engine.build_visits([outside, inside], [ZONE], now=T + timedelta(minutes=2))
check("two minutes in, still not (it may be passing through)", len(v), 0)
v = engine.build_visits([outside, inside], [ZONE], now=T + timedelta(minutes=8))
check("eight minutes in and nowhere else since: at the mine", len(v), 1)
check("...since the ping that saw it there", v[0]["enter"] if v else None, T)
check("...and still open", v[0]["open"] if v else None, True)
left = {"plate": "20H01397", "dt": T + timedelta(minutes=3), "lat": 15.93, "lng": 106.64, "speed": 40, "status": ""}
v = engine.build_visits([outside, inside, left], [ZONE], now=T + timedelta(hours=2))
check("a truck that left after three minutes only passed through", len(v), 0)

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
