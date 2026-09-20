# -*- coding: utf-8 -*-
"""Routes: named sequences of Locations, and one route per truck.

Run: python tests/test_route_store.py   (PYTHONIOENCODING=utf-8 on Windows)

Decided 18/09/2026. The order trucks pass through Locations used to be a
fixed role mapping on the Parameter page. It is a ROUTE now: a named,
ordered list of Locations, built on the Route page. A truck belongs to
exactly one route, set on the declaration list, and cannot be on another.
The engine's role mapping is deliberately untouched by any of this.
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
from app import geofence                                          # noqa: E402
from app.models import db, Anchor, Truck, Route, User, Subcontractor  # noqa: E402
from app.models import DailyList                                  # noqa: E402

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
    zones = {a.role: a.id for a in Anchor.query.all() if a.role}
    roles_before = dict(zones)
    for who, role, adm in (("planner1", "planner", False), ("sup1", "supervisor", False),
                           ("mon1", "monitor", False), ("boss", "admin", True)):
        u = User(username=who, role=role, is_admin=adm)
        u.set_password("x" * 12)
        db.session.add(u)
    for p in ("20H01381", "20H01385", "20H01393"):
        db.session.add(Truck(plate=p, status="active"))
    db.session.commit()
    ids = {u.username: u.id for u in User.query.all()}
    check("boot added truck.route_id", hasattr(Truck.query.first(), "route_id"), True)

c = app.test_client()


def as_user(name):
    with c.session_transaction() as s:
        s["_user_id"] = str(ids[name])
        s["_fresh"] = True


print("who may build a route")
as_user("mon1")
check("a monitor may read", c.get("/api/route-seqs").status_code, 200)
check("...but not create", c.post("/api/route-seqs", json={"name": "X"}).status_code, 403)
as_user("planner1")
check("a planner may not create either - admin only since 20/09",
      c.post("/api/route-seqs", json={"name": "Z"}).status_code, 403)
as_user("boss")
r = c.post("/api/route-seqs", json={"name": "XPPL → Chan May", "fronthaul": []})
check("an admin may create", r.status_code, 200)
RID = r.get_json()["id"]
check("...and the answer carries the routes", len(r.get_json()["routes"]), 1)
check("a second route with the same name is refused",
      c.post("/api/route-seqs", json={"name": "xppl → chan may"}).status_code, 409)
check("a nameless route is refused", c.post("/api/route-seqs", json={"name": " "}).status_code, 400)

print("\nthe fronthaul")
seq = [zones["xppl"], zones["border"], zones["ql49"], zones["port"]]
r = c.put("/api/route-seqs/%d" % RID, json={"fronthaul": seq})
check("locations go in, in order", r.status_code, 200)
got = next(x for x in r.get_json()["routes"] if x["id"] == RID)
check("...and come back in that order", [s["id"] for s in got["fronthaul"]], seq)
check("...with their names", got["fronthaul"][0]["name"], "XPPL Mine")
check("a location twice in one leg is refused",
      c.put("/api/route-seqs/%d" % RID, json={"fronthaul": seq + [zones["xppl"]]}).status_code, 400)
check("an unknown location is refused",
      c.put("/api/route-seqs/%d" % RID, json={"fronthaul": [999]}).status_code, 400)

print("\nthe backhaul is its own leg (user, 20/09)")
# The way home need not retrace the way out, and the stops it shares with the
# fronthaul are passed a second time - which is why they are not a clash.
back = [zones["port"], zones["ql49"], zones["border"], zones["xppl"]]
r = c.put("/api/route-seqs/%d" % RID, json={"backhaul": back})
check("the way home goes in", r.status_code, 200)
got = next(x for x in r.get_json()["routes"] if x["id"] == RID)
check("...in its own order", [s["id"] for s in got["backhaul"]], back)
check("...and the fronthaul is untouched", [s["id"] for s in got["fronthaul"]], seq)
check("the same location in both legs is fine",
      set(s["id"] for s in got["fronthaul"]) & set(s["id"] for s in got["backhaul"]) != set(), True)
check("a new route starts with neither leg described",
      c.post("/api/route-seqs", json={"name": "Bare"}).get_json()["routes"][0]["backhaul"], [])

with app.app_context():
    a = Anchor.query.get(zones["ql49"])
    geofence.retire(a, "tester")
check("a retired zone cannot be added to a route",
      c.put("/api/route-seqs/%d" % RID, json={"fronthaul": [zones["ql49"]]}).status_code, 400)
check("...nor to the way home",
      c.put("/api/route-seqs/%d" % RID, json={"backhaul": [zones["ql49"]]}).status_code, 400)
with app.app_context():
    # Un-retire it for the rest of the test. Retiring clears the role by design
    # (geofence.retire), and that is this test's doing, not the route code's -
    # so put the role back too, or the "roles untouched" check at the end would
    # blame the wrong thing.
    a = Anchor.query.get(zones["ql49"])
    a.retired_at = None
    a.role = "ql49"
    db.session.commit()
r = c.put("/api/route-seqs/%d" % RID, json={"name": "Corridor A"})
check("renaming works", next(x for x in r.get_json()["routes"] if x["id"] == RID)["name"], "Corridor A")

print("\none truck, one route")
r2 = c.post("/api/route-seqs", json={"name": "Ango → Chan May", "fronthaul": []}).get_json()["id"]
as_user("mon1")
check("a monitor may not lock a truck",
      c.put("/api/trucks/20H01381/route", json={"route_id": RID}).status_code, 403)
as_user("sup1")
r = c.put("/api/trucks/20H01381/route", json={"route_id": RID})
check("a supervisor may", r.status_code, 200)
check("...and is told the route", r.get_json()["route"], "Corridor A")
check("the plate is normalised on the way in",
      c.put("/api/trucks/20h-01385/route", json={"route_id": RID}).status_code, 200)
routes = c.get("/api/route-seqs").get_json()
check("the route lists its trucks",
      next(x for x in routes if x["id"] == RID)["trucks"], ["20H01381", "20H01385"])
r = c.put("/api/trucks/20H01381/route", json={"route_id": r2})
check("moving a truck to another route", r.status_code, 200)
routes = c.get("/api/route-seqs").get_json()
check("...takes it off the first", next(x for x in routes if x["id"] == RID)["trucks"], ["20H01385"])
check("...and onto the second", next(x for x in routes if x["id"] == r2)["trucks"], ["20H01381"])
check("a truck is never on two routes",
      sum(len(x["trucks"]) for x in routes), 2)
check("null clears the lock",
      c.put("/api/trucks/20H01381/route", json={"route_id": None}).get_json()["route_id"], None)
check("an unknown truck is a 404",
      c.put("/api/trucks/99X99999/route", json={"route_id": RID}).status_code, 404)
check("an unknown route is a 404",
      c.put("/api/trucks/20H01381/route", json={"route_id": 4242}).status_code, 404)

print("\ndeleting a route with trucks on it")
as_user("planner1")
check("a planner may not delete one",
      c.delete("/api/route-seqs/%d" % RID).status_code, 403)
as_user("boss")
r = c.delete("/api/route-seqs/%d" % RID)
check("is refused while a truck is locked to it", r.status_code, 409)
check("...naming the truck", r.get_json()["trucks"], ["20H01385"])
r = c.delete("/api/route-seqs/%d?force=1" % RID)
check("force deletes it", r.status_code, 200)
with app.app_context():
    check("...and unlocks the truck",
          Truck.query.filter_by(plate="20H01385").first().route_id, None)
    check("...leaving no truck pointing at a missing route",
          Truck.query.filter(Truck.route_id.isnot(None)).count(), 0)

print("\nthe declaration list carries the route")
as_user("sup1")
c.put("/api/trucks/20H01393/route", json={"route_id": r2})
with app.app_context():
    sub = Subcontractor.query.first()
    sub_id = sub.id if sub else None      # the object is bound to this context; keep the id
    dl = DailyList(list_date="2026-09-20", subcontractor_id=sub_id, state="draft")
    db.session.add(dl)
    db.session.commit()
r = c.post("/api/shift/list", json={"date": "2026-09-20",
                                    "subcontractor_id": sub_id,
                                    "rows": [{"plate": "20H01393", "activity": "FH"}]})
check("a declaration saves", r.status_code, 200)
row = next(x for x in r.get_json()["rows"] if x["plate"] == "20H01393")
check("...and its row names the truck's route", row.get("route"), "Ango → Chan May")
check("...with the id", row.get("route_id"), r2)

print("\nnone of this touched the engine's role mapping")
with app.app_context():
    check("roles are exactly as they were",
          {a.role: a.id for a in Anchor.query.all() if a.role}, roles_before)

print("\n  %d FAILING" % FAIL if FAIL else "\n  all pass")
sys.exit(1 if FAIL else 0)
