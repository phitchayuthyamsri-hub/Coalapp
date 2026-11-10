# -*- coding: utf-8 -*-
"""A Ngo Warehouse in the GPS cycle (10/11/2026).

Run: python tests/test_ango_stop.py   (PYTHONIOENCODING=utf-8 on Windows)

The cycle builder knew the mine, the border, QL49 and the port, so a trip
planned Mine : A Ngo showed no A Ngo at all on the Scorecard. It now records
the A Ngo stop on the way out (after the loaded border crossing, before the
port if the trip goes on), and for a trip that ends at A Ngo the border
crossing home. Everything it found before comes out exactly the same.
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


XPPL, LOAD, BORDER, QL49, PORT, ANGO = 1, 2, 3, 4, 5, 6
ROLES = {"xppl": XPPL, "loading": LOAD, "border": BORDER, "ql49": QL49, "port": PORT, "ango": ANGO}
T0 = datetime(2026, 11, 2, 7, 0)


def trip(plate, stops):
    """stops: [(anchor, hours from T0 in, hours out)]"""
    return [{"plate": plate, "anchor_id": a, "enter": T0 + timedelta(hours=i),
             "exit": T0 + timedelta(hours=o)} for a, i, o in stops]


def run(stops, roles=ROLES):
    seqs = engine.recompute_sequences(trip("A1", stops), roles)
    return seqs[0] if seqs else {}


print("Mine : A Ngo")
c = run([(XPPL, 0, 2), (LOAD, 0.5, 1.5), (BORDER, 6, 9), (ANGO, 10, 12), (BORDER, 16, 17), (XPPL, 22, 23)])
check("A Ngo on the way out", (c["ango_in"], c["ango_out"]), (T0 + timedelta(hours=10), T0 + timedelta(hours=12)))
check("the border crossing home after it", c["border_home_out"], T0 + timedelta(hours=17))
check("no port, so no port-based return leg", (c["chan_may_in"], c["lalay_back_in"]), (None, None))
check("back at the mine as before", c["xppl_r"], T0 + timedelta(hours=22))

print("\nMine : A Ngo : Chan May")
c = run([(XPPL, 0, 2), (BORDER, 6, 9), (ANGO, 10, 11), (QL49, 13, 14), (PORT, 20, 26),
         (QL49, 29, 30), (BORDER, 36, 37), (XPPL, 44, 45)])
check("A Ngo between the border and QL49", c["ango_in"], T0 + timedelta(hours=10))
check("QL49 and the port found as before", (c["ql49_out_in"], c["chan_may_in"]),
      (T0 + timedelta(hours=13), T0 + timedelta(hours=20)))
check("return leg after the port as before", c["lalay_back_in"], T0 + timedelta(hours=36))
check("no border_home: the trip went on to the port", c["border_home_in"], None)

print("\nMine : Chan May, home by way of A Ngo")
c = run([(XPPL, 0, 2), (BORDER, 6, 9), (QL49, 12, 13), (PORT, 20, 26), (ANGO, 30, 31),
         (BORDER, 36, 37), (XPPL, 44, 45)])
check("an A Ngo visit after the port is not the stop out", (c["ango_in"], c["border_home_in"]), (None, None))
check("port and return leg untouched", (c["chan_may_in"], c["lalay_back_in"]),
      (T0 + timedelta(hours=20), T0 + timedelta(hours=36)))

print("\nno A Ngo zone set up")
c = run([(XPPL, 0, 2), (BORDER, 6, 9), (ANGO, 10, 12), (XPPL, 22, 23)],
        {k: v for k, v in ROLES.items() if k != "ango"})
check("nothing recorded, nothing breaks", (c["ango_in"], c["xppl_r"]), (None, T0 + timedelta(hours=22)))

print("\none mine stay: stepped out and back (10/11/2026)")
seqs = engine.recompute_sequences(trip("A1", [(XPPL, 0, 1), (XPPL, 2, 3), (LOAD, 2.2, 2.8), (BORDER, 8, 10),
                                             (XPPL, 30, 31)]), ROLES)
check("out at 1 h, back at 2 h, nowhere between: one trip", len(seqs), 2)
check("...starting at the first arrival", seqs[0]["xppl_in"], T0)
check("...leaving at the LAST exit before the border", seqs[0]["xppl_out"], T0 + timedelta(hours=3))
check("...and it reaches the border", seqs[0]["lalay_out_in"], T0 + timedelta(hours=8))
seqs = engine.recompute_sequences(trip("A1", [(XPPL, 0, 1), (XPPL, 40, 41), (BORDER, 46, 47)]), ROLES)
check("back after more than a day with nothing seen: two trips (GPS outage)", len(seqs), 2)
seqs = engine.recompute_sequences(trip("A1", [(XPPL, 0, 1), (BORDER, 6, 8), (XPPL, 20, 21)]), ROLES)
check("a location in between: two trips, as before", [len(seqs), seqs[0]["xppl_out"]], [2, T0 + timedelta(hours=1)])

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
