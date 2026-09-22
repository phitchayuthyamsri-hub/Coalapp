# -*- coding: utf-8 -*-
"""When two providers report the same plate, TCT's word stands.

Run: python tests/test_provider_guard.py   (PYTHONIOENCODING=utf-8 on Windows)

22/09/2026. Twenty-three plates were fed by both TCT and Viettel, with the
two providers' positions 100 km apart at the same minute. User: "always
priority on TCT first, Viettel has low reliability". A Viettel position
for a plate TCT has positioned in the last 24 hours is dropped; where TCT
has gone quiet, Viettel fills in.
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
from app.models import db, GpsPing                                # noqa: E402

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
    # TCT spoke for 20H01378 an hour ago; for 20H00715 last in June (dead box).
    db.session.add_all([
        GpsPing(plate="20H01378", dt=NOW - timedelta(hours=1), lat=16.24, lng=107.28, source="api:tct"),
        GpsPing(plate="20H00715", dt=NOW - timedelta(days=80), lat=16.34, lng=106.98, source="api:tct2"),
    ])
    db.session.commit()

    print("rank")
    check("TCT outranks nobody above it", gi._outranked_by("tct"), ())
    check("the second TCT account is TCT", gi._provider_key("api:tct2"), "tct")
    check("Viettel is outranked by TCT and Adsun", gi._outranked_by("viettel"), ("tct", "adsun"))

    print("\nwhat Viettel may add")
    batch = [ping("20H01378", 15.86, 106.66), ping("20H00715", 16.30, 106.90),
             ping("20H01442", 16.30, 106.90)]
    dropped = [p["plate"] for p in gi.foreign_to(batch, "api:viettel", now=NOW)]
    check("not a plate TCT positioned an hour ago", dropped, ["20H01378"])
    check("a plate whose TCT box died in June is Viettel's to report",
          "20H00715" in dropped, False)
    check("a plate TCT never had is Viettel's", "20H01442" in dropped, False)
    check("TCT is never dropped for Viettel",
          gi.foreign_to([ping("20H01378", 16.24, 107.28, 5)], "api:tct", now=NOW), [])

    print("\nstoring")
    n = gi._store(batch, "api:viettel")
    db.session.commit()
    check("two of the three Viettel positions are stored", n, 2)
    check("the TCT truck's Viettel position is not",
          GpsPing.query.filter_by(plate="20H01378", source="api:viettel").count(), 0)

    print("\nthe stored trail")
    db.session.add(GpsPing(plate="20H01378", dt=NOW - timedelta(hours=2), lat=15.80, lng=106.60,
                           speed=20.0, source="api:viettel"))       # an old wrong row, as prod has
    db.session.commit()
    pts = gi._stored_trail("20H01378", NOW - timedelta(hours=3), NOW + timedelta(hours=1))
    check("TCT's rows alone when TCT is in the range",
          [(p["lat"], p["lng"]) for p in pts], [(16.24, 107.28)])
    pts = gi._stored_trail("20H00715", NOW - timedelta(hours=3), NOW + timedelta(hours=1))
    check("Viettel's rows when TCT is not", [(p["lat"], p["lng"]) for p in pts], [(16.3, 106.9)])

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
