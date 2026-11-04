# -*- coding: utf-8 -*-
"""Storing a pull never loads the history between its oldest and newest ping.

Run: python tests/test_store_stale_ping.py   (PYTHONIOENCODING=utf-8 on Windows)

04/11/2026: the fleet grew by 92 trucks, some with trackers that went quiet
months ago and keep reporting their last fix (43H12895: 28/07). The duplicate
check read every stored ping between the batch's oldest and newest time, so
each minute pull loaded every Viettel ping since July - 800-900 MB - and the
kernel killed it, swapping the shared droplet.
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

from sqlalchemy import event                  # noqa: E402
from app import create_app                    # noqa: E402
from app import gps_ingest as gi              # noqa: E402
from app.models import db, GpsPing            # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


NOW = datetime(2026, 11, 4, 19, 0)
OLD = datetime(2026, 7, 28, 12, 48, 35)
gi.foreign_to = lambda pings, source, now=None, registered=None: []

app = create_app()
with app.app_context():
    # Three months of one live truck's history on the same account.
    t = OLD
    rows = []
    while t < NOW:
        rows.append(GpsPing(plate="43H18545", dt=t, lat=16.3, lng=106.9, speed=0,
                            status="park", source="api:viettel", address="x"))
        t += timedelta(minutes=30)
    db.session.add_all(rows)
    # The quiet tracker's last fix, stored long ago, without an address.
    db.session.add(GpsPing(plate="43H12895", dt=OLD, lat=16.31, lng=106.97, speed=0,
                           status="offline", source="api:viettel", address=""))
    db.session.commit()
    history = len(rows)
    del rows
    db.session.expunge_all()          # a fresh session, as each cron run has

    loaded = [0]

    @event.listens_for(GpsPing, "load")
    def _count(target, context):
        loaded[0] += 1

    batch = [
        {"plate": "43H12895", "dt": OLD, "lat": 16.31, "lng": 106.97, "speed": 0,
         "status": "offline", "address": "QL15D"},                  # stale, already stored
        {"plate": "43H18545", "dt": NOW, "lat": 16.32, "lng": 106.95, "speed": 30,
         "status": "moving", "address": "La Lay"},                  # new
    ]
    n = gi._store(batch, "api:viettel")
    seen = loaded[0]
    check("the new position is stored", n, 1)
    check("...the stale one is not stored twice",
          GpsPing.query.filter_by(plate="43H12895").count(), 1)
    check("...but gets the address it lacked",
          GpsPing.query.filter_by(plate="43H12895").first().address, "QL15D")
    check("the duplicate check loaded only the batch's own rows, not %d" % history,
          seen <= 2, True)
    check("storing the same batch again adds nothing", gi._store(batch, "api:viettel"), 0)

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
