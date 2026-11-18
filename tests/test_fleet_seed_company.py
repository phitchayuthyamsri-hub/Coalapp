# -*- coding: utf-8 -*-
"""The fleet the tool page reads carries each truck's company (18/11/2026).

Run: python tests/test_fleet_seed_company.py   (PYTHONIOENCODING=utf-8 on Windows)

The Fleet page has a Company column and its export has to fill it, but the seed
that writes the page's fleet never sent the company, so it stayed blank.
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
from app.models import db, Truck, Subcontractor                   # noqa: E402
from sync_tool_state import build_fleet                           # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(58) + ("" if ok else "got %r want %r" % (got, want)))


app = create_app()
with app.app_context():
    s = Subcontractor(name="Bao Binh Test", short="BBC-T")
    n = Subcontractor(name="No Short Name Co")
    db.session.add_all([s, n]); db.session.flush()
    db.session.add_all([Truck(plate="74H02558", subcontractor_id=s.id), Truck(plate="20H01364", subcontractor_id=n.id), Truck(plate="99Z00001")])
    db.session.commit()
    f = build_fleet()
    check("the company id for the picker", f["74H02558"]["companyId"], s.id)
    check("the company's short name for the column", f["74H02558"]["company"], "BBC-T")
    check("the full name when it has no short one", f["20H01364"]["company"], "No Short Name Co")
    check("a truck with no company stays blank", (f["99Z00001"]["companyId"], f["99Z00001"]["company"]), ("", ""))

print("\n" + ("%d FAILED" % FAIL if FAIL else "ALL PASS"))
sys.exit(1 if FAIL else 0)
