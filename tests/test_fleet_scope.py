# -*- coding: utf-8 -*-
"""Who sees which trucks on the Fleet page, and who may change them.

Run: python tests/test_fleet_scope.py   (PYTHONIOENCODING=utf-8 on Windows)

21/10/2026: a truck belongs to a subcontractor company. A company's logins see
its trucks and any truck the company has declared on a sheet (a colleague's
upload included); Bac Nam, which owns every truck today, sees them all. Only
the admin adds a truck, removes one, or sets its company - before this, any
login could do all three through /api/fleet.
"""
import json
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
from app.models import (db, User, Truck, Subcontractor, DailyList,  # noqa: E402
                        DailyListRow)

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


app = create_app()
ids = {}
with app.app_context():
    def sub(name):
        s = Subcontractor.query.filter_by(name=name).first() or Subcontractor(name=name, short=name)
        db.session.add(s)
        db.session.flush()
        return s.id
    BN, HS = sub("Bac Nam"), sub("Hoanh Son")
    for name, role, sid, adm in (("boss", "admin", None, True), ("huytrv", "subcontractor", BN, False),
                                 ("hieu", "subcontractor", HS, False), ("tri", "subcontractor", HS, False),
                                 ("anh", "supervisor", None, False)):
        u = User(username=name, role=role, is_admin=adm)
        u.set_password("x" * 12)
        u.subcontractor_id = sid
        db.session.add(u)
        db.session.flush()
        ids[name] = str(u.id)
    db.session.add_all([Truck(plate="20H01469", subcontractor_id=BN),
                        Truck(plate="20H01474", subcontractor_id=BN),
                        Truck(plate="75C11111", subcontractor_id=HS),
                        Truck(plate="75C22222")])            # no company yet
    # Uploaded by one Hoanh Son login: the other must see it too.
    dl = DailyList(list_date="2026-10-22", subcontractor_id=HS, state="draft")
    db.session.add(dl)
    db.session.flush()
    db.session.add(DailyListRow(list_id=dl.id, plate="75C22222", key="75C22222", note="BH"))
    db.session.commit()


def client(who):
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = ids[who]
        s["_fresh"] = True
    return c


def plates(who):
    return sorted(t["plate"] for t in client(who).get("/api/fleet").get_json())


print("who sees what")
check("the admin sees the whole fleet", plates("boss"), ["20H01469", "20H01474", "75C11111", "75C22222"])
check("an operations desk sees the whole fleet", plates("anh"), ["20H01469", "20H01474", "75C11111", "75C22222"])
check("Bac Nam sees its trucks", plates("huytrv"), ["20H01469", "20H01474"])
check("Hoanh Son: its truck and what its colleague uploaded", plates("tri"), ["75C11111", "75C22222"])
seed = client("hieu").get("/api/tool/seed.js").get_data(as_text=True)
check("...and the tool page is seeded with the same", ("75C11111" in seed, "20H01469" in seed), (True, False))
check("the company is named on each truck",
      {t["plate"]: t["company"] for t in client("boss").get("/api/fleet").get_json()}["75C11111"], "Hoanh Son")

print("\nthe Subcontractor page and Process (21/10/2026)")
# Hoanh Son's first login: no sheet of its own for the day.
hint = client("hieu").get("/api/shift/suggest?date=2026-10-23").get_json()
check("the GPS hint lists only Hoanh Son's trucks, not the fleet",
      sorted(r["plate"] for r in hint.get("rows", [])), ["75C11111", "75C22222"])
check("...and Bac Nam's lists only Bac Nam's",
      sorted(r["plate"] for r in client("huytrv").get("/api/shift/suggest?date=2026-10-23").get_json().get("rows", [])),
      ["20H01469", "20H01474"])
with app.app_context():
    dlb = DailyList(list_date="2026-10-22", subcontractor_id=BN, state="draft")
    db.session.add(dlb)
    db.session.commit()
fl = client("hieu").get("/api/shift/flow").get_json()
companies = sorted({c.get("company") or "" for d in fl.get("days", []) for c in d["companies"]})
check("Process shows a subcontractor its own company only", companies, ["Hoanh Son"])
fl = client("anh").get("/api/shift/flow").get_json()
companies = sorted({c.get("company") for d in fl.get("days", []) for c in d["companies"]} - {None})
check("...and the desks every company", companies, ["Bac Nam", "Hoanh Son"])

print("\nwho may change what")
r = client("hieu").post("/api/fleet", json={"plate": "75C99999", "status": "online"})
check("a subcontractor cannot add a truck", r.status_code, 403)
r = client("boss").post("/api/fleet", json={"plate": "75C99999", "status": "online"})
today = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d")
with app.app_context():
    t = Truck.query.filter_by(plate="75C99999").first()
    check("the admin can", (r.status_code, t is not None), (200, True))
    check("...and it is in effect from the day it was added", t.eff_from, today)
check("a subcontractor edits its own truck",
      client("hieu").post("/api/fleet", json={"plate": "75C11111", "driver": "Nguyen"}).status_code, 200)
check("...not another company's",
      client("hieu").post("/api/fleet", json={"plate": "20H01469", "driver": "x"}).status_code, 403)
check("only the admin sets a company",
      client("hieu").post("/api/fleet", json={"plate": "75C11111", "subcontractor_id": BN}).status_code, 403)
client("boss").post("/api/fleet", json={"plate": "75C22222", "subcontractor_id": HS})
with app.app_context():
    check("...which the admin can", Truck.query.filter_by(plate="75C22222").first().subcontractor_id, HS)
check("a subcontractor cannot remove a truck", client("hieu").delete("/api/fleet/75C11111").status_code, 403)
check("the admin can", client("boss").delete("/api/fleet/75C99999").status_code, 200)
with app.app_context():
    check("...and it is gone", Truck.query.filter_by(plate="75C99999").first(), None)
    check("a refused removal left the truck", Truck.query.filter_by(plate="75C11111").first() is not None, True)

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
