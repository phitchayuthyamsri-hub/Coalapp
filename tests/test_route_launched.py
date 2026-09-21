# -*- coding: utf-8 -*-
"""A route not launched yet does not demand its trucks on the declaration.

Run: python tests/test_route_launched.py   (PYTHONIOENCODING=utf-8 on Windows)

21/09/2026. The fleet grew from 20 to 47 when the whole Bac Nam list was
imported, and the new 27 are on the A Ngo routes, which are built but not
running. Submit refused the day's 20-truck sheet for those 27. A route now
says whether it has launched; a truck on one that has not is not asked for.
A truck with no route at all still is - only an explicit "not yet" excuses.
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
from app import shift_routes                                      # noqa: E402
from app.models import db, Truck, Route, User, Subcontractor      # noqa: E402
from app.models import DailyList, DailyListRow                    # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(60)
          + ("" if ok else "got %r want %r" % (got, want)))


app = create_app()
with app.app_context():
    boss = User(username="boss", role="admin", is_admin=True)
    boss.set_password("x" * 12)
    db.session.add(boss)
    sub = Subcontractor.query.first() or Subcontractor(name="Bac Nam")
    db.session.add(sub)
    running = Route(name="Mine : Chan May", kind="fronthaul", sequence=[])
    idle = Route(name="Mine : A Ngo", kind="fronthaul", sequence=[])
    db.session.add_all([running, idle])
    db.session.commit()
    check("a new route starts launched", idle.launched, True)
    for p, r in (("20H01498", running.id), ("20H01499", running.id),
                 ("20C10615", idle.id), ("20C10763", idle.id), ("20H00001", None)):
        db.session.add(Truck(plate=p, status="active", route_id=r))
    dl = DailyList(list_date="2026-09-22", subcontractor_id=sub.id, state="draft")
    db.session.add(dl)
    db.session.flush()
    for p in ("20H01498", "20H01499"):
        db.session.add(DailyListRow(list_id=dl.id, plate=p, key=p, note="FH",
                                    ready=True, state="pending"))
    db.session.commit()
    boss_id, dl_id, sub_id, idle_id = boss.id, dl.id, sub.id, idle.id

    gaps = shift_routes._fleet_gaps(db.session.get(DailyList, dl_id), sub_id)
    check("launched: every unanswered truck is a gap", gaps,
          ["20C10615", "20C10763", "20H00001"])

c = app.test_client()
with c.session_transaction() as s:
    s["_user_id"] = str(boss_id)
    s["_fresh"] = True

r = c.put("/api/route-seqs/%d" % idle_id, json={"launched": False})
check("admin marks a route not launched", r.status_code, 200)
row = [x for x in r.get_json()["routes"] if x["id"] == idle_id][0]
check("payload carries launched", row["launched"], False)

with app.app_context():
    gaps = shift_routes._fleet_gaps(db.session.get(DailyList, dl_id), sub_id)
    check("its trucks are no longer asked for", gaps, ["20H00001"])
    check("a truck with no route is still asked for", "20H00001" in gaps, True)

r = c.put("/api/route-seqs/%d" % idle_id, json={"name": "Mine : A Ngo"})
with app.app_context():
    check("a save that does not mention it keeps it",
          db.session.get(Route, idle_id).launched, False)

r = c.put("/api/route-seqs/%d" % idle_id, json={"launched": True})
with app.app_context():
    gaps = shift_routes._fleet_gaps(db.session.get(DailyList, dl_id), sub_id)
    check("launched again: asked for again", gaps,
          ["20C10615", "20C10763", "20H00001"])

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
