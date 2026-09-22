# -*- coding: utf-8 -*-
"""When two providers report the same plate, the fleet register decides;
TCT outranks only where the register is silent.

Run: python tests/test_provider_guard.py   (PYTHONIOENCODING=utf-8 on Windows)

22/09/2026. Twenty-three plates were fed by both TCT and Viettel, with the
two providers' positions 100 km apart at the same minute. Settled on
20H01378: the register said Viettel, and TCT's device was another vehicle
parked at the port while the truck was loaded at the border. The register
is the authority; for a plate it does not name, TCT's word stands where
TCT has spoken in the last 24 hours, else Viettel fills in.
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
from app import gps_ingest as gi                                  # noqa: E402
from app import shift_routes as sr                                # noqa: E402
from app.models import db, GpsPing, Truck                         # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(62)
          + ("" if ok else "got %r want %r" % (got, want)))


NOW = datetime(2026, 9, 22, 21, 0)
ping = lambda plate, lat, lng, m=0: {"plate": plate, "dt": NOW + timedelta(minutes=m),
                                     "lat": lat, "lng": lng, "speed": 10.0, "status": ""}

app = create_app()
with app.app_context():
    db.session.add_all([
        Truck(plate="20H01378", status="active", gps_provider="Viettel"),
        Truck(plate="20H00708", status="active", gps_provider="TCT"),
        Truck(plate="20H00728", status="active", gps_provider=""),       # unnamed
        Truck(plate="20H00715", status="active", gps_provider=""),       # unnamed, TCT box dead
        # TCT spoke for the unnamed 20H00728 an hour ago; for 20H00715 in June.
        GpsPing(plate="20H00728", dt=NOW - timedelta(hours=1), lat=16.3, lng=106.9, source="api:tct"),
        GpsPing(plate="20H00715", dt=NOW - timedelta(days=80), lat=16.34, lng=106.98, source="api:tct2"),
    ])
    db.session.commit()

    print("the register decides")
    batch = [ping("20H01378", 16.24, 107.28), ping("20H00708", 16.3, 106.9)]
    check("TCT may not report the Viettel truck",
          [p["plate"] for p in gi.foreign_to(batch, "api:tct", now=NOW)], ["20H01378"])
    check("...nor may the second TCT account",
          [p["plate"] for p in gi.foreign_to(batch, "api:tct2", now=NOW)], ["20H01378"])
    check("Viettel may not report the TCT truck",
          [p["plate"] for p in gi.foreign_to(batch, "api:viettel", now=NOW)], ["20H00708"])

    print("\nfor a plate the register does not name, TCT first")
    batch = [ping("20H00728", 15.86, 106.66), ping("20H00715", 16.30, 106.90),
             ping("99X99999", 16.30, 106.90)]
    dropped = [p["plate"] for p in gi.foreign_to(batch, "api:viettel", now=NOW)]
    check("Viettel may not report a plate TCT positioned an hour ago", dropped, ["20H00728"])
    check("...but may report one whose TCT box died in June", "20H00715" in dropped, False)
    check("...and a stranger", "99X99999" in dropped, False)
    check("TCT is never dropped for Viettel on an unnamed plate",
          gi.foreign_to([ping("20H00728", 16.3, 106.9, 5)], "api:tct", now=NOW), [])

    print("\nstoring")
    n = gi._store([ping("20H01378", 16.24, 107.28), ping("20H00708", 16.3, 106.9)], "api:tct")
    db.session.commit()
    check("only the TCT truck's TCT position is stored", n, 1)
    check("the Viettel truck's TCT position is not",
          GpsPing.query.filter_by(plate="20H01378", source="api:tct").count(), 0)
    n = gi._store([ping("20H01378", 15.86, 106.66)], "api:viettel")
    db.session.commit()
    check("its Viettel position is", n, 1)

    print("\nthe pages read only each truck's own provider")
    # Rows stored before the guard existed, as prod has.
    db.session.add_all([
        GpsPing(plate="20H01378", dt=NOW - timedelta(hours=2), lat=16.31, lng=108.02,
                speed=0.0, source="api:tct"),                        # phantom at the port
        GpsPing(plate="20H00708", dt=NOW - timedelta(hours=2), lat=15.0, lng=106.0,
                speed=0.0, source="api:viettel"),                    # phantom
    ])
    db.session.commit()
    rows = sr._own_pings(GpsPing.query).order_by(GpsPing.dt).all()
    seen = sorted({(r.plate, r.source) for r in rows})
    check("the Viettel truck's TCT row is not read", ("20H01378", "api:tct") in seen, False)
    check("the TCT truck's Viettel row is not read", ("20H00708", "api:viettel") in seen, False)
    check("their own rows are", ("20H01378", "api:viettel") in seen and ("20H00708", "api:tct") in seen, True)
    check("unnamed plates are read from anyone",
          ("20H00728", "api:tct") in seen and ("20H00715", "api:tct2") in seen, True)

    print("\nthe stored trail")
    pts = gi._stored_trail("20H01378", NOW - timedelta(hours=3), NOW + timedelta(hours=1))
    check("the Viettel truck's trail is Viettel's alone",
          [(p["lat"], p["lng"]) for p in pts], [(15.86, 106.66)])
    db.session.add(GpsPing(plate="20H00715", dt=NOW - timedelta(hours=1), lat=16.3, lng=106.9,
                           speed=5.0, source="api:viettel"))
    db.session.commit()
    pts = gi._stored_trail("20H00715", NOW - timedelta(hours=3), NOW + timedelta(hours=1))
    check("an unnamed plate's trail is the best provider present", [(p["lat"], p["lng"]) for p in pts], [(16.3, 106.9)])

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
