# -*- coding: utf-8 -*-
"""A position for a plate the fleet registers with another provider is
another vehicle, and is not stored.

Run: python tests/test_provider_guard.py   (PYTHONIOENCODING=utf-8 on Windows)

22/09/2026. Twenty-three plates were fed by both TCT and Viettel, with the
two providers' positions 100 km apart at the same minute. The fleet register
names each truck's provider; the other provider's rows are dropped.
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
from app.models import db, Truck, GpsPing                         # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(62)
          + ("" if ok else "got %r want %r" % (got, want)))


T = datetime(2026, 9, 22, 20, 0)
ping = lambda plate, lat, lng, m=0: {"plate": plate, "dt": T + timedelta(minutes=m),
                                     "lat": lat, "lng": lng, "speed": 10.0, "status": ""}

app = create_app()
with app.app_context():
    db.session.add_all([Truck(plate="20H01378", status="active", gps_provider="Viettel"),
                        Truck(plate="20H00708", status="active", gps_provider="TCT"),
                        Truck(plate="20H00728", status="active", gps_provider="")])
    db.session.commit()

    print("which provider each plate belongs to")
    reg = gi.registered_providers()
    check("Viettel truck", reg.get("20H01378"), "viettel")
    check("TCT truck", reg.get("20H00708"), "tct")
    check("a truck with no provider is not registered", "20H00728" in reg, False)

    print("\nwhat a provider may report")
    batch = [ping("20H01378", 16.24, 107.28), ping("20H00708", 16.3, 106.9),
             ping("20H00728", 16.3, 106.9), ping("99X99999", 16.3, 106.9)]
    f = [p["plate"] for p in gi.foreign_to(batch, "api:tct")]
    check("TCT may not report the Viettel truck", f, ["20H01378"])
    f = [p["plate"] for p in gi.foreign_to(batch, "api:tct2")]
    check("...nor may the second TCT account", f, ["20H01378"])
    f = [p["plate"] for p in gi.foreign_to(batch, "api:viettel")]
    check("Viettel may not report the TCT truck", f, ["20H00708"])
    check("an unregistered plate and a stranger are left alone",
          any(p["plate"] in ("20H00728", "99X99999") for p in gi.foreign_to(batch, "api:tct")), False)

    print("\nstoring")
    n = gi._store(batch, "api:tct")
    db.session.commit()
    check("three of the four TCT positions are stored", n, 3)
    check("the Viettel truck's TCT position is not",
          GpsPing.query.filter_by(plate="20H01378").count(), 0)
    n = gi._store([ping("20H01378", 15.86, 106.66)], "api:viettel")
    db.session.commit()
    check("its Viettel position is", n, 1)

    print("\nthe stored trail")
    # An older wrong row, as prod has: stored before the guard existed.
    db.session.add(GpsPing(plate="20H01378", dt=T - timedelta(hours=1), lat=16.24, lng=107.28,
                           speed=20.0, source="api:tct"))
    db.session.commit()
    pts = gi._stored_trail("20H01378", T - timedelta(hours=2), T + timedelta(hours=1))
    check("shows only the truck's own provider", [(p["lat"], p["lng"]) for p in pts], [(15.86, 106.66)])
    pts = gi._stored_trail("20H00728", T - timedelta(hours=2), T + timedelta(hours=1))
    check("a truck with no registered provider shows everything", len(pts), 1)

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
