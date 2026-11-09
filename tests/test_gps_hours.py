# -*- coding: utf-8 -*-
"""The timing blob says which hours each truck sent GPS in (09/11/2026).

Run: python tests/test_gps_hours.py   (PYTHONIOENCODING=utf-8 on Windows)

The Daily report tells "did not come" from "No GPS" by it: a truck that sent
nothing around its plan time cannot be said to have stayed away.
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

from app import create_app                        # noqa: E402
from app.models import db, GpsPing, Truck         # noqa: E402
import sync_tool_state as sts                     # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(60) + ("" if ok else "got %r want %r" % (got, want)))


app = create_app()
with app.app_context():
    now = datetime.now(sts._PING_TZ).replace(tzinfo=None)
    day = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    old = now - timedelta(days=sts.GPS_HOURS_DAYS + 5)
    db.session.add(Truck(plate="20H-014.69", status="online"))
    for dt in (day + timedelta(hours=7, minutes=5), day + timedelta(hours=7, minutes=40),
               day + timedelta(hours=21), old):
        db.session.add(GpsPing(plate="20H-014.69", dt=dt, lat=16.6, lng=106.6))
    db.session.commit()
    timing, n = sts.build_timing()
    gh = timing.get("gpsHours") or {}
    d = day.strftime("%Y-%m-%d")
    plates = gh.get("plates", {})
    check("the plate is keyed the way the page keys it", sorted(plates), ["20H01469"])
    check("hours 07 and 21 of that day, and nothing else", plates.get("20H01469", {}).get(d), (1 << 7) | (1 << 21))
    check("a position older than the window is left out", len(plates.get("20H01469", {})), 1)
    check("the window start is given", gh.get("from"),
          (now - timedelta(days=sts.GPS_HOURS_DAYS)).strftime("%Y-%m-%d"))

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
