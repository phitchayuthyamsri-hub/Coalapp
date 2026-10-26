# -*- coding: utf-8 -*-
"""A declaration answers at once; the GPS hint is stamped behind it.

Run: python tests/test_hint_background.py   (PYTHONIOENCODING=utf-8 on Windows)

26/10/2026: Bac Nam's 27/10 upload failed twice with an HTML error page. The
upload itself takes a quarter of a second; stamping the GPS hint inside the
same request took 6 s on a quiet box and past gunicorn's 30 s on the busy one.
The stamp now runs after the answer, and still carries the declaration's time.
"""
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

_tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL="sqlite:///" + os.path.join(_tmp, "t.db").replace("\\", "/"),
    SECRET_KEY="test-only-not-a-real-key", COALAPP_ENV="")

from app import create_app                                        # noqa: E402
from app import shift_routes as sr                                # noqa: E402
from app.models import db, User, Truck, Subcontractor, DailyList  # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


RUN = (datetime.utcnow() + sr.LOCAL_OFFSET + timedelta(days=1)).strftime("%Y-%m-%d")

# A slow GPS step, as on the busy server.
_real = sr._gps_view


def slow_view(day, only):
    time.sleep(2.0)
    return _real(day, only)


sr._gps_view = slow_view
sr.HINT_IN_BACKGROUND = True

app = create_app()
with app.app_context():
    sub = Subcontractor.query.filter_by(name="Bac Nam").first() or Subcontractor(name="Bac Nam")
    db.session.add(sub)
    db.session.flush()
    u = User(username="huytrv@bacnam", role="subcontractor")
    u.set_password("x" * 12)
    u.subcontractor_id = sub.id
    db.session.add(u)
    db.session.add(Truck(plate="20H01469", status="online", subcontractor_id=sub.id))
    db.session.commit()
    uid, SID = str(u.id), sub.id

c = app.test_client()
with c.session_transaction() as s:
    s["_user_id"] = uid
    s["_fresh"] = True

t = time.time()
r = c.post("/api/shift/list", json={"date": RUN, "subcontractor_id": SID, "rows": [
    {"plate": "20H01469", "activity": "BH", "arrive_date": RUN, "arrive": "08:00"}]})
took = time.time() - t
stamped_at_once = None
with app.app_context():
    stamped_at_once = DailyList.query.filter_by(list_date=RUN).first().hint_at
check("the declaration is saved", r.status_code, 200)
check("...and answers without waiting for the GPS step", took < 1.5, True)
check("the hint is not there yet at that moment", stamped_at_once, None)

hint_at = None
for _ in range(50):
    time.sleep(0.2)
    with app.app_context():
        db.session.remove()
        dl = DailyList.query.filter_by(list_date=RUN).first()
        if dl.hint_at:
            hint_at, by, rows = dl.hint_at, dl.hint_by, len((dl.hint or {}).get("rows", []))
            break
check("the hint arrives behind it", hint_at is not None, True)
if hint_at:
    check("...stamped with the declaration's time, not the end of the GPS step",
          hint_at <= datetime.utcnow() - timedelta(seconds=1.5), True)
    check("...by whoever declared", by, "huytrv@bacnam")
    check("...with the company's truck in it", rows, 1)

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
