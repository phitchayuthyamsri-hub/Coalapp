# -*- coding: utf-8 -*-
"""Visits: the 300 m edge margin and pass-through checkpoints (10/11/2026).

Run: python tests/test_zone_margin.py   (PYTHONIOENCODING=utf-8 on Windows)

1-10 Nov, points were missing because a truck stood 60-300 m outside a zone's
drawn edge (back at the mine, A Ngo, the border), or because a sparse provider
sent ONE position while the truck passed the border / QL49 and the 5-minute
dwell threw the pass away. A position within 300 m of the edge now counts, and
at a pass-through checkpoint one position is the pass.
"""
import os
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from app import engine  # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64) + ("" if ok else "got %r want %r" % (got, want)))


# a 1 km square zone at about 16.3N 106.9E
SQ = [[16.300, 106.900], [16.309, 106.900], [16.309, 106.9094], [16.300, 106.9094]]
KM_LAT = 1 / 111.32
T0 = datetime(2026, 11, 2, 7, 0)


def zone(role, dwell=5):
    return {"id": 1, "name": role, "polygon": SQ, "role": role, "min_dwell_min": dwell, "versions": []}


def visits(points, z):
    pings = [{"plate": "A1", "dt": T0 + timedelta(minutes=m), "lat": la, "lng": ln} for m, la, ln in points]
    return engine.build_visits(pings, [z])


print("the 300 m margin")
check("inside the drawn zone", engine.in_zone(16.304, 106.904, SQ), True)
check("200 m south of the edge: in", engine.in_zone(16.300 - 0.2 * KM_LAT, 106.904, SQ), True)
check("500 m south of the edge: out", engine.in_zone(16.300 - 0.5 * KM_LAT, 106.904, SQ), False)
check("far away: out", engine.in_zone(15.75, 106.71, SQ), False)
near = 16.300 - 0.15 * KM_LAT
v = visits([(0, 16.29, 106.904), (10, near, 106.904), (20, near, 106.905), (30, near, 106.904), (40, 16.29, 106.904)], zone("xppl"))
check("a truck parked 150 m outside the mine: a visit", (len(v), v[0]["enter"] if v else None), (1, T0 + timedelta(minutes=10)))

print("\npass-through checkpoints")
one = [(0, 16.29, 106.904), (5, 16.304, 106.904), (10, 16.32, 106.904)]
check("border: one position = the pass", len(visits(one, zone("border"))), 1)
check("QL49: one position = the pass", len(visits(one, zone("ql49"))), 1)
check("Dakrong (detour): one position = the pass", len(visits(one, zone("detour"))), 1)
check("the mine keeps its 5-minute dwell (a drive-by is not a stay)", len(visits(one, zone("xppl"))), 0)
check("the port: one position is the visit (nobody drives past it)", len(visits(one, zone("port"))), 1)
check("A Ngo keeps its dwell (Chan May trucks drive past)", len(visits(one, zone("ango"))), 0)
check("a zone with no role keeps its dwell too", len(visits(one, zone(""))), 0)

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
