# -*- coding: utf-8 -*-
"""The Truck Status grid from the GPS, beside the declared one.

Run: python tests/test_gps_status_grid.py   (PYTHONIOENCODING=utf-8 on Windows)

06/10/2026: "If I used data from GPS + logic given, can I have the separate
similar one? For repair just left blank." Same grid, one cell per truck per
day, from the day's GPS snapshot - the supervisor's pull, with the system's
own leg rule (seen at the port since it last left the mine = BH, else FH).
"""
import os
import sys
import tempfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

_tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL="sqlite:///" + os.path.join(_tmp, "t.db").replace("\\", "/"),
    SECRET_KEY="test-only-not-a-real-key", COALAPP_ENV="")

from app import create_app                                        # noqa: E402
from app import tool_link                                         # noqa: E402
from app.models import (db, Subcontractor, DailyList, DailyListRow,  # noqa: E402
                        GpsSnapshot)

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


def g(plate, status, why, seen="2026-10-04 13:35", where="Lalay border"):
    return {"plate": plate, "status": status, "why": why,
            "seen_at": seen if status or why.startswith("seen") else None,
            "location": where if status else ""}


app = create_app()
with app.app_context():
    sub = Subcontractor.query.filter_by(name="Bac Nam").first() or Subcontractor(name="Bac Nam")
    db.session.add(sub)
    db.session.flush()
    dl = DailyList(list_date="2026-10-05", subcontractor_id=sub.id, state="confirmed")
    db.session.add(dl)
    db.session.flush()
    db.session.add(DailyListRow(list_id=dl.id, plate="20H01397", key="20H01397",
                                note="Repair", ready=False, state="approved"))
    db.session.add(DailyListRow(list_id=dl.id, plate="20H01469", key="20H01469",
                                note="FH", ready=True, state="approved"))
    db.session.add(GpsSnapshot(day="2026-10-05", taken_at=datetime(2026, 10, 4, 6, 36),
                               taken_by="anh.lp@nam-tien.vn", data={"rows": [
        g("20H01469", "BH", "passed the port at 04/10 09:12"),
        g("20H01397", "FH", "not yet at the port on this run", where="Workshop"),
        g("20H01389", "", "no GPS position in the last 24 hours"),
        g("20H01474", "FH", "not yet at the port on this run"),
    ]}))
    db.session.add(GpsSnapshot(day="2026-10-06", taken_at=datetime(2026, 10, 5, 6, 36),
                               taken_by="anh.lp@nam-tien.vn", data={"rows": [
        g("20H01469", "FH", "not yet at the port on this run", seen="2026-10-05 13:30"),
        g("20H01397", "", "seen by GPS, but not yet at any checkpoint - leg unknown"),
    ]}))
    db.session.commit()

    st = tool_link._gps_status(None)
    c = st["cell"]

    print("the grid")
    check("one column per GPS snapshot day", st["dates"], ["2026-10-05", "2026-10-06"])
    check("every truck the GPS reported", st["plates"], ["20H01389", "20H01397", "20H01469", "20H01474"])
    check("the leg is the GPS's, not the declaration's", c["20H01469"], {"2026-10-05": "BH", "2026-10-06": "FH"})
    check("...and the hover says why", st["tip"]["20H01469"]["2026-10-05"],
          "GPS 04/10 13:35 · Lalay border · passed the port at 04/10 09:12")
    check("the column header names the pull, local time", st["taken"]["2026-10-05"], "04/10 13:36 by anh.lp")

    print("\nblank cells")
    check("declared Repair: blank, whatever the GPS said", c["20H01397"].get("2026-10-05"), None)
    check("...and the hover says so", st["tip"]["20H01397"]["2026-10-05"], "declared not running - no leg")
    check("no GPS: blank", c["20H01389"], {})
    check("...with the reason on hover", st["tip"]["20H01389"]["2026-10-05"],
          "no GPS position in the last 24 hours")
    check("leg unknown: blank", c["20H01397"].get("2026-10-06"), None)

    print("\na subcontractor sees its own trucks")
    only = tool_link._gps_status({"20H01469"})
    check("scoped to the plates given", only["plates"], ["20H01469"])

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
