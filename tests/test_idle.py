# -*- coding: utf-8 -*-
"""How long a truck has been standing, from its pings.

Run: python tests/test_idle.py   (PYTHONIOENCODING=utf-8 on Windows)

22/09/2026. The map pop-up shows the provider's address and an idle time,
as the TCT portal does. The provider does not send the idle time; it is
walked back through the stored pings.
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
from app import shift_routes as sr                                # noqa: E402
from app.models import db, GpsPing                                # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(60)
          + ("" if ok else "got %r want %r" % (got, want)))


T = datetime(2026, 9, 22, 16, 0)
LA = (16.3498, 106.9874)                       # La Lay
H = lambda h: T + timedelta(hours=h)
still = lambda h, lat=LA[0], lng=LA[1]: (H(h), lat, lng, 0.0)
moving = lambda h, lat=LA[0], lng=LA[1]: (H(h), lat, lng, 45.0)

check("moving now: not idle", sr._idle_since([still(0), moving(1)]), None)
check("stood since the first standing ping",
      sr._idle_since([moving(0), still(0.5), still(1), still(2)]), H(0.5))
check("a wobble of a few metres is still standing",
      sr._idle_since([still(0), still(1, LA[0] + 0.0005, LA[1]), still(2)]), H(0))
check("a stop at another place is another stop",
      sr._idle_since([still(0, LA[0] + 0.05, LA[1]), moving(1), still(2), still(3)]), H(2))
check("one standing ping: idle since that ping", sr._idle_since([still(5)]), H(5))
check("no pings: nothing to say", sr._idle_since([]), None)
check("creeping at 2 km/h counts as standing",
      sr._idle_since([(H(0), LA[0], LA[1], 2.0), still(1)]), H(0))

print("\nthe ping keeps the address")
app = create_app()
with app.app_context():
    db.session.add(GpsPing(plate="20H00795", dt=T, lat=LA[0], lng=LA[1], speed=0.0,
                           address="X. La Lay, Quảng Trị"))
    db.session.commit()
    check("stored and read back", GpsPing.query.first().address, "X. La Lay, Quảng Trị")

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
