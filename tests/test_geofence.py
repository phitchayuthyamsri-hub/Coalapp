# -*- coding: utf-8 -*-
"""Geofences: a change never rewrites history, and there is one store.

Run: python tests/test_geofence.py   (PYTHONIOENCODING=utf-8 on Windows)

Decided 18/09/2026. Before this the Monitor recomputed every visit from every
ping against the CURRENT shape on every request, so moving a boundary
re-judged months of history; and the Parameter page kept its own copy of the
zones in the browser, so the Monitor never saw an edit made there at all.
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

from app import engine                                     # noqa: E402
from app import create_app                                 # noqa: E402
from app import geofence                                   # noqa: E402
from app.models import db, Anchor, AnchorVersion, User     # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(60)
          + ("" if ok else "got %r want %r" % (got, want)))


# Two squares: SMALL sits inside BIG. A point at (0.5, 0.5) is in both; a
# point at (1.5, 1.5) is in BIG only.
SMALL = [[0, 0], [0, 1], [1, 1], [1, 0]]
BIG = [[0, 0], [0, 2], [2, 2], [2, 0]]
T0 = datetime(2026, 9, 18, 8, 0)
CHANGE = datetime(2026, 9, 18, 10, 0)


def t(minutes):
    return T0 + timedelta(minutes=minutes)


def ping(minutes, lat, lng):
    return {"plate": "20H01381", "dt": t(minutes), "lat": lat, "lng": lng,
            "speed": 0, "status": ""}


# -- the engine -----------------------------------------------------------------
print("engine: which shape judges a ping")
zone = {"id": 1, "name": "Mine", "polygon": BIG, "min_dwell_min": 0,
        "versions": [{"valid_from": None, "polygon": SMALL, "min_dwell_min": 0},
                     {"valid_from": CHANGE, "polygon": BIG, "min_dwell_min": 0}],
        "retired_at": None}
check("before the change, the old shape", engine.anchor_at(zone, t(0))[0], SMALL)
check("at the exact moment of the change, the new one",
      engine.anchor_at(zone, CHANGE)[0], BIG)
check("after it, the new one", engine.anchor_at(zone, t(200))[0], BIG)
plain = {"id": 2, "name": "Port", "polygon": SMALL, "min_dwell_min": 5}
check("a zone with no versions is judged by its plain polygon",
      engine.anchor_at(plain, t(0)), (SMALL, 5))
born = {"id": 3, "name": "New", "polygon": SMALL, "min_dwell_min": 0,
        "versions": [{"valid_from": CHANGE, "polygon": SMALL, "min_dwell_min": 0}]}
check("a zone did not exist before its first version",
      engine.anchor_at(born, t(0)), (None, 0))
gone = dict(zone, retired_at=CHANGE)
check("a retired zone stops matching from that moment",
      engine.anchor_at(gone, CHANGE), (None, 0))
check("...and still matched just before it", engine.anchor_at(gone, t(119))[0], SMALL)

print("\nengine: history stays put")
# The truck sits at (1.5, 1.5) the whole time: outside SMALL, inside BIG.
pings = [ping(m, 1.5, 1.5) for m in range(0, 240, 10)]
visits = engine.build_visits(pings, [zone])
check("no visit is invented for the hours before the boundary moved",
      all(v["enter"] >= CHANGE for v in visits), True)
check("...and the visit that does exist starts AT the change",
      [v["enter"] for v in visits], [CHANGE])
# Under the old engine - current shape for everything - the whole span would
# have been one visit from 08:00. Prove that is exactly what we no longer do.
old_way = engine.build_visits(pings, [{"id": 1, "name": "Mine", "polygon": BIG,
                                       "min_dwell_min": 0}])
check("(the un-versioned reading would have started it at 08:00)",
      [v["enter"] for v in old_way], [T0])

# The truck is at (0.5, 0.5) - inside both shapes - and the zone is retired.
pings2 = [ping(m, 0.5, 0.5) for m in range(0, 240, 10)]
v2 = engine.build_visits(pings2, [gone])
check("a retired zone keeps the visit it had", len(v2), 1)
check("...closed at the last ping before retirement", v2[0]["exit"], t(110))
check("...and nothing after", v2[0]["open"], False)

# Dwell threshold is the one in force when the visit opened.
dz = {"id": 4, "name": "Dwell", "polygon": SMALL, "min_dwell_min": 60,
      "versions": [{"valid_from": None, "polygon": SMALL, "min_dwell_min": 5},
                   {"valid_from": CHANGE, "polygon": SMALL, "min_dwell_min": 60}]}
short_before = [ping(0, 0.5, 0.5), ping(10, 0.5, 0.5), ping(20, 5, 5)]
short_after = [ping(130, 0.5, 0.5), ping(140, 0.5, 0.5), ping(150, 5, 5)]
check("a 10-minute stop before the change passes the old 5-minute dwell",
      len(engine.build_visits(short_before, [dz])), 1)
check("the same stop after the change fails the new 60-minute dwell",
      len(engine.build_visits(short_after, [dz])), 0)

# -- the store ------------------------------------------------------------------
print("\nstore: one table, versioned")
app = create_app()
with app.app_context():
    n_anchor = Anchor.query.count()
    check("boot backfilled one version per seeded zone",
          AnchorVersion.query.count(), n_anchor)
    check("...all of them 'since the beginning'",
          all(v.valid_from is None for v in AnchorVersion.query.all()), True)
    check("...and running the backfill again adds nothing", geofence.ensure_versions(), 0)

    a = Anchor.query.filter_by(role="xppl").first()
    before = list(a.polygon)
    n0 = AnchorVersion.query.filter_by(anchor_id=a.id).count()

    check("renaming does not make a version",
          geofence.update(a, {"name": "XPPL Mine (renamed)"}, "tester"), False)
    check("...the name changed", a.name, "XPPL Mine (renamed)")
    check("re-sending the same shape does not make a version",
          geofence.update(a, {"polygon": before}, "tester"), False)
    check("...even with float noise",
          geofence.update(a, {"polygon": [[p[0] + 1e-9, p[1]] for p in before]}, "tester"),
          False)
    moved = [[p[0] + 0.01, p[1] + 0.01] for p in before]
    check("moving the boundary makes a version",
          geofence.update(a, {"polygon": moved}, "tester"), True)
    vs = AnchorVersion.query.filter_by(anchor_id=a.id).order_by(AnchorVersion.id).all()
    check("...exactly one more", len(vs), n0 + 1)
    check("...dated now, on the ping clock",
          abs((vs[-1].valid_from - geofence.ping_clock_now()).total_seconds()) < 5, True)
    check("...signed", vs[-1].set_by, "tester")
    check("...and the current shape is the new one", a.polygon, moved)
    check("changing the dwell makes a version too",
          geofence.update(a, {"min_dwell_min": 9}, "tester"), True)

    fe = {x["id"]: x for x in geofence.for_engine()}
    check("for_engine carries every version, oldest first",
          [v["valid_from"] is None for v in fe[a.id]["versions"]][:1], [True])
    check("...and the first is the original shape", fe[a.id]["versions"][0]["polygon"], before)

    try:
        geofence.update(a, {"polygon": [[0, 0], [1, 1]]}, "tester")
        check("a two-point polygon is refused", False, True)
    except ValueError:
        check("a two-point polygon is refused", True, True)

    new = geofence.create({"name": "Ango Yard", "polygon": SMALL, "min_dwell_min": 5},
                          "tester")
    nv = AnchorVersion.query.filter_by(anchor_id=new.id).all()
    check("a new zone has one version", len(nv), 1)
    check("...that takes effect now, not since the beginning",
          nv[0].valid_from is not None, True)
    check("...so it is in the engine list", new.id in {x["id"] for x in geofence.for_engine()}, True)

    geofence.retire(new, "tester")
    check("a retired zone is kept", Anchor.query.get(new.id) is not None, True)
    check("...stamped", new.retired_at is not None, True)
    check("...out of the current shapes", len(geofence.current_polygons()),
          Anchor.query.filter(Anchor.retired_at.is_(None)).count())
    check("...but still in the engine list, for history",
          new.id in {x["id"] for x in geofence.for_engine()}, True)

    port = Anchor.query.filter_by(role="port").first()
    r = geofence.set_roles({"xppl": a.id, "port": port.id, "bogus": a.id, "ql49": None})
    check("roles are set one zone per role", r.get("xppl"), a.id)
    check("...a role left out is cleared", "ql49" in r, False)
    check("...an unknown role is ignored", "bogus" in r, False)
    check("...a retired zone cannot hold one",
          geofence.set_roles({"xppl": new.id}).get("xppl"), None)

    # The API: reads for everyone logged in, writes for admins only.
    u = User(username="viewer", role="monitor", is_admin=False); u.set_password("x" * 12)
    adm = User(username="boss", role="admin", is_admin=True); adm.set_password("x" * 12)
    db.session.add_all([u, adm]); db.session.commit()
    uid, aid_ = u.id, adm.id
    a_id = a.id            # the object above is bound to this context; keep the id
c = app.test_client()
with c.session_transaction() as s:
    s["_user_id"] = str(uid); s["_fresh"] = True
print("\napi: who may do what")
r = c.get("/api/anchors")
check("anyone logged in may read the zones", r.status_code, 200)
check("...retired ones are not in the default list",
      any(x["retired_at"] for x in r.get_json()), False)
check("...but are there on request",
      any(x["retired_at"] for x in c.get("/api/anchors?include=retired").get_json()), True)
check("a viewer may not move one",
      c.put("/api/anchors/%d" % a_id, json={"polygon": SMALL}).status_code, 403)
check("...nor create", c.post("/api/anchors", json={"name": "x", "polygon": SMALL}).status_code, 403)
check("...nor retire", c.delete("/api/anchors/%d" % a_id).status_code, 403)
with c.session_transaction() as s:
    s["_user_id"] = str(aid_); s["_fresh"] = True
r = c.put("/api/anchors/%d" % a_id, json={"polygon": before})
check("an admin may", r.status_code, 200)
check("...and is told whether that made a version", r.get_json().get("versioned"), True)
r = c.put("/api/anchors/%d" % a_id, json={"polygon": before})
check("...and that a no-op did not", r.get_json().get("versioned"), False)
check("a bad polygon is a 400",
      c.post("/api/anchors", json={"name": "x", "polygon": [[0, 0]]}).status_code, 400)

print("\n  %d FAILING" % FAIL if FAIL else "\n  all pass")
sys.exit(1 if FAIL else 0)
