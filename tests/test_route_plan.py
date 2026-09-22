# -*- coding: utf-8 -*-
"""Each truck is planned along its own route.

Run: python tests/test_route_plan.py   (PYTHONIOENCODING=utf-8 on Windows)

22/09/2026. The corridor planner knows one loop, mine to Chan May and home.
A truck on Mine : A Ngo or A Ngo : Chan May was planned as if it ran that
loop: promised a port it never reaches, home twenty hours late. Now the
revision and the week hand each truck to the planner for its route. Corridor
trucks still go through the corridor planner and their plan does not move.
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
from app import planner                                           # noqa: E402
from app.models import (db, Anchor, RouteLeg, Route, Truck, Subcontractor,  # noqa: E402
                        DailyList, DailyListRow)

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


SQ = [[16.0, 106.0], [16.0, 106.01], [16.01, 106.01], [16.01, 106.0]]
DAY = "2026-09-23"

app = create_app()
with app.app_context():
    # Locations as they stand on prod: the corridor's roles plus A Ngo.
    z = {}
    for name, role, typ, bays, mins, wo, wc, bo, bc in (
            ("QL49", "ql49", "border", None, None, "19:00", "23:59", "00:01", "05:00"),
            ("Chan May port", "port", "unload", 3, 60, "08:00", "17:00", "08:00", "17:00"),
            ("XPPL Mine", "xppl", "", None, None, "", "", "", ""),
            ("XPPL Loading area", "loading", "load", 2, 60, "", "", "", ""),
            ("Lalay border", "border", "border", None, None, "15:00", "19:00", "08:00", "17:00"),
            ("A Ngo Warehouse", "ango", "load_unload", 1, 60, "08:00", "17:00", "08:00", "17:00")):
        a = Anchor.query.filter_by(name=name).first() or Anchor(name=name, polygon=SQ)
        a.role, a.loc_type, a.loading_bays, a.loading_time_min = role, typ, bays, mins
        a.window_out_open, a.window_out_close = wo, wc
        a.window_back_open, a.window_back_close = bo, bc
        a.polygon = a.polygon or SQ
        db.session.add(a)
        db.session.flush()
        z[role] = a.id
    # Legs, measured ONE way only where the operation measured them one way.
    for key, fr, to, km in (("a3_a4", "xppl", "loading", 0.05), ("a4_a5", "loading", "border", 117.55),
                            ("a5_a7", "border", "ango", 8.0), ("a7_a1", "ango", "ql49", 46.0),
                            ("a1_a2", "ql49", "port", 116.0), ("mine_border", "xppl", "border", 117.55)):
        lg = RouteLeg.query.filter_by(leg_key=key).first() or RouteLeg(leg_key=key)
        lg.from_anchor_id, lg.to_anchor_id, lg.road_km, lg.speed = z[fr], z[to], km, 40.0
        lg.label = key
        db.session.add(lg)
    cm = Route(name="Mine : Chan May", kind="fronthaul",
               sequence=[z["xppl"], z["loading"], z["border"], z["ql49"], z["port"]])
    ma = Route(name="Mine : A Ngo", kind="fronthaul",
               sequence=[z["xppl"], z["loading"], z["border"], z["ango"]])
    ac = Route(name="A Ngo : Chan May", kind="fronthaul",
               sequence=[z["ango"], z["ql49"], z["port"]])
    db.session.add_all([cm, ma, ac])
    db.session.flush()
    sub = Subcontractor.query.first() or Subcontractor(name="Bac Nam")
    db.session.add(sub)
    db.session.flush()
    for plate, rid in (("20H01498", cm.id), ("20H01499", None), ("20C10615", ma.id),
                       ("20C10763", ac.id)):
        db.session.add(Truck(plate=plate, status="active", route_id=rid))
    dl = DailyList(list_date=DAY, subcontractor_id=sub.id, state="confirmed")
    db.session.add(dl)
    db.session.flush()
    for plate, hhmm in (("20H01498", "06:00"), ("20H01499", "06:15"),
                        ("20C10615", "06:30"), ("20C10763", "06:45")):
        db.session.add(DailyListRow(list_id=dl.id, plate=plate, key=plate, note="BH",
                                    ready=True, state="approved", arrive_date=DAY,
                                    arrive_hhmm=hhmm))
    db.session.commit()

    from app import shift_routes as sr
    with app.test_request_context():
        data = sr._revision_data(DAY, None)
    rows = {r["plate"]: r for r in data["rows"]}
    check("every approved truck is planned", sorted(rows), ["20C10615", "20C10763", "20H01498", "20H01499"])

    print("\ncorridor trucks: the corridor planner, unchanged")
    cfg = planner.load_config()
    ref = {r["plate"]: r for r in planner.plan_trucks(
        [("20H01498", datetime(2026, 9, 23, 6, 0)), ("20H01499", datetime(2026, 9, 23, 6, 15))], cfg)}
    iso = lambda d: d.strftime("%Y-%m-%dT%H:%M")
    for p in ("20H01498", "20H01499"):
        check("%s: same times as the corridor planner alone" % p,
              (rows[p]["t"]["arrive_mine"], rows[p]["t"]["arrive_port"], rows[p]["t"]["back"]),
              (iso(ref[p]["arrive_mine"]), iso(ref[p]["arrive_port"]), iso(ref[p]["arrive_mine_back"])))
    check("a truck with no route is a corridor truck", rows["20H01499"]["start_role"], "xppl")
    check("the corridor's way home is still chosen", rows["20H01498"]["route"] in ("hue", "ql49"), True)

    print("\nMine : A Ngo")
    t = rows["20C10615"]["t"]
    check("starts at the mine at the declared time", t["arrive_mine"], "2026-09-23T06:30")
    check("loads at the loading area", t["load_start"] is not None and t["load_end"] > t["load_start"], True)
    check("crosses the border after the 15:00 gate and the paperwork",
          t["cross_border"] >= "2026-09-23T15:00", True)
    check("reaches A Ngo after crossing", t["arrive_ango"] > t["cross_border"], True)
    check("A Ngo work is one hour", (t["ango_start"] is not None) and t["ango_end"] > t["ango_start"], True)
    check("no port on this loop", t["arrive_port"], None)
    check("home is the mine, after A Ngo", t["back"] > t["ango_end"], True)
    check("the row says where its run starts", rows["20C10615"]["start_role"], "xppl")
    check("the loop is complete - the reverse legs answered", rows["20C10615"]["complete"], True)
    check("...and the plan says a leg was borrowed",
          any("measured the other way" in n for n in rows["20C10615"]["notes"]), True)
    check("its cycle is far shorter than a Chan May loop",
          rows["20C10615"]["cycle_hours"] < 30, True)

    print("\nA Ngo : Chan May")
    t = rows["20C10763"]["t"]
    check("the run starts at A Ngo at the declared time", rows["20C10763"]["start_role"], "ango")
    check("...and that time anchors the row", t["arrive_mine"], "2026-09-23T06:45")
    check("loads at A Ngo first", t["ango_start"], "2026-09-23T08:00")
    check("QL49 waits for its 19:00 window", t["ql49_in"] >= "2026-09-23T19:00", True)
    check("unloads at the port", t["unload_start"] is not None, True)
    check("home is A Ngo", t["back_ango"], t["back"])
    check("no border on this loop", t["arrive_border"], None)

    print("\na week rolls a truck round its route again and again")
    with app.test_request_context():
        wk = sr._week_data(DAY, None, True)
    loops = sorted(r["t"]["arrive_mine"] for r in wk["rows"] if r["plate"] == "20C10615")
    check("Mine : A Ngo turns several loops in the week", len(loops) >= 4, True)
    check("...each starting after the last came home", loops == sorted(set(loops)), True)
    backs = [r["t"]["back"] for r in wk["rows"] if r["plate"] == "20C10615"]
    check("...and each loop has its own way home", len(set(backs)), len(backs))

    print("\nthe Monitor reads these")
    with app.app_context():
        pass
    c = app.test_client()
    from app.models import User, PlanSnapshot
    with app.app_context():
        u = User(username="mon", role="monitor")
        u.set_password("x" * 12)
        db.session.add(u)
        db.session.add(PlanSnapshot(week_start=sr._week_start(DAY).strftime("%Y-%m-%d"), day=DAY,
                                    subcontractor_id=None, issued_by="t", rows=data["rows"], figures=[]))
        db.session.commit()
        uid = str(u.id)
    with c.session_transaction() as s:
        s["_user_id"] = uid
        s["_fresh"] = True
    tr = c.get("/api/shift/track?date=" + DAY).get_json()
    by = {r["plate"]: r for r in tr["rows"]}
    cell = lambda r, leg, key: [x for x in r[leg] if x["key"] == key][0]
    check("Mine : A Ngo has a plan time in At A Ngo", cell(by["20C10615"], "fh", "ango")["plan"], rows["20C10615"]["t"]["arrive_ango"])
    check("...and in Leaves A Ngo", cell(by["20C10615"], "fh", "ango_out")["plan"], rows["20C10615"]["t"]["ango_end"])
    check("...and none at the port", cell(by["20C10615"], "fh", "port")["na"], True)
    check("A Ngo : Chan May's home cell is A Ngo", cell(by["20C10763"], "bh", "ango")["plan"], rows["20C10763"]["t"]["back"])

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
