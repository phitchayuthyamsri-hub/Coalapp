# -*- coding: utf-8 -*-
"""A company declares its own trucks, not every truck in the table (05/11/2026).

Run: python tests/test_fleet_gaps_own_company.py   (PYTHONIOENCODING=utf-8 on Windows)

PTS, Hoanh Son and BBC joined the fleet with 71 trucks. Bac Nam has no
committed roster, so its "every truck answers" check fell back to the whole
truck table - and Bac Nam's 06/11 sheet could not be submitted until it
declared 71 trucks that are not its own.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

_tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL="sqlite:///" + os.path.join(_tmp, "t.db").replace("\\", "/"),
    SECRET_KEY="test-only-not-a-real-key", COALAPP_ENV="")

from app import create_app                                        # noqa: E402
from app import shift_routes as sr                                # noqa: E402
from app.models import db, Truck, Subcontractor, DailyList, DailyListRow  # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


app = create_app()
with app.app_context():
    bn = Subcontractor.query.filter_by(name="Bac Nam").first() or Subcontractor(name="Bac Nam")
    bbc = Subcontractor.query.filter_by(name="Bao Binh").first() or Subcontractor(name="Bao Binh", short="BBC")
    db.session.add_all([bn, bbc])
    db.session.flush()
    db.session.add_all([
        Truck(plate="20H01381", status="online", subcontractor_id=bn.id),
        Truck(plate="20H01378", status="online", subcontractor_id=bn.id),
        Truck(plate="20H09999", status="online"),                      # no company on it
        Truck(plate="43H22582", status="online", subcontractor_id=bbc.id),
        Truck(plate="29E33234", status="online", subcontractor_id=bbc.id),
        Truck(plate="43H12895", status="deactivated", subcontractor_id=bbc.id)])
    dl = DailyList(list_date="2026-11-06", subcontractor_id=bn.id, state="draft")
    db.session.add(dl)
    db.session.flush()
    db.session.add(DailyListRow(list_id=dl.id, plate="20H01381", key="20H01381", note="FH"))
    db.session.commit()

    gaps = sr._fleet_gaps(dl, bn.id)
    check("Bac Nam is asked for its own undeclared truck", "20H01378" in gaps, True)
    check("...and a truck with no company, as before", "20H09999" in gaps, True)
    check("...but not for BBC's trucks", [g for g in gaps if g in ("43H22582", "29E33234")], [])
    check("...nor a deactivated one", "43H12895" in gaps, False)

    db.session.add(DailyListRow(list_id=dl.id, plate="20H01378", key="20H01378", note="BH"))
    db.session.add(DailyListRow(list_id=dl.id, plate="20H09999", key="20H09999", note="Repair"))
    db.session.commit()
    check("once its own trucks are declared, nothing is missing", sr._fleet_gaps(dl, bn.id), [])

    d2 = DailyList(list_date="2026-11-06", subcontractor_id=bbc.id, state="draft")
    db.session.add(d2)
    db.session.commit()
    check("BBC's own sheet asks for BBC's trucks",
          sorted(g for g in sr._fleet_gaps(d2, bbc.id) if g != "20H09999"), ["29E33234", "43H22582"])

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
