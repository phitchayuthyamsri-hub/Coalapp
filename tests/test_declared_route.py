# -*- coding: utf-8 -*-
"""The route a truck runs is declared per truck, per day.

Run: python tests/test_declared_route.py   (PYTHONIOENCODING=utf-8 on Windows)

30/09/2026, "Truck can now run with multiple routing ... Adding routing in
template and expect them to run". A truck used to have one standing route on
the fleet and every page read that. Now the declaration carries a Route - a
column on the sheet, a column on the page - and the plan, the Monitor and the
GPS stamps follow what was declared for that day. The fleet's route is what a
declaration that does not say falls back to, and declaring never changes it.
"""
import io
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

from openpyxl import Workbook                                     # noqa: E402

from app import create_app                                        # noqa: E402
from app import actuals, readiness_import                         # noqa: E402
from app import shift_routes as sr                                # noqa: E402
from app.models import (db, Anchor, RouteLeg, Route, Truck, Subcontractor,  # noqa: E402
                        User, DailyList, DailyListRow, ActualStamp, PlanSnapshot)

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(66)
          + ("" if ok else "got %r want %r" % (got, want)))


def sheet(rows, route_col=True):
    """A readiness sheet as the template lays it out. -> path"""
    wb = Workbook()
    ws = wb.active
    ws.title = "Readiness"
    head = ["No", "Plate", "Driver"] + (["Route"] if route_col else []) + [
        "Status", "Loaded / Empty", "Location", "Date arrive Mine", "Time arrive Mine",
        "Back in service", "Remark"]
    ws.append(head)
    for i, r in enumerate(rows, 1):
        ws.append([i, r[0], ""] + ([r[1]] if route_col else []) + [r[2], "Empty", "", r[3], r[4], "", ""])
    p = os.path.join(_tmp, "s%d.xlsx" % len(os.listdir(_tmp)))
    wb.save(p)
    return p


SQ = [[16.0, 106.0], [16.0, 106.01], [16.01, 106.01], [16.01, 106.0]]
now_l = datetime.utcnow() + sr.LOCAL_OFFSET
TODAY = now_l.strftime("%Y-%m-%d")
DAY = (now_l + timedelta(days=1)).strftime("%Y-%m-%d")           # tomorrow: the sheet's day
NEXT = (now_l + timedelta(days=2)).strftime("%Y-%m-%d")
FAR = (now_l + timedelta(days=10)).strftime("%Y-%m-%d")
sr.SAME_DAY_RULE_FROM = "2000-01-01"

app = create_app()
with app.app_context():
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
    sub = Subcontractor.query.first() or Subcontractor(name="Bac Nam")
    db.session.add(sub)
    db.session.flush()
    # The fleet's standing routes: one on the corridor, one on Mine : A Ngo,
    # one with none at all.
    for plate, rid in (("20H01498", cm.id), ("20C10615", ma.id), ("20H01499", None)):
        db.session.add(Truck(plate=plate, status="active", route_id=rid))
    ids = {}
    for name, role in (("sub1", "subcontractor"), ("adm", "admin"), ("mon", "monitor")):
        u = User(username=name, role=role, is_admin=(role == "admin"))
        u.set_password("x" * 12)
        if role == "subcontractor":
            u.subcontractor_id = sub.id
        db.session.add(u)
        db.session.flush()
        ids[role] = str(u.id)
    db.session.commit()
    SID, CM, MA, AC = sub.id, cm.id, ma.id, ac.id
    ROLES = dict(z)


def client(role):
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = ids[role]
        s["_fresh"] = True
    return c


def row_routes():
    with app.app_context():
        return {r.plate: r.route_id for r in DailyListRow.query.all()}


print("the sheet's Route column is read")
got = readiness_import.parse(sheet([("20H01498", "Mine : A Ngo", "BH", DAY, "06:00")]), strict=True)
check("the route comes through as the sheet wrote it", got["rows"][0].get("route"), "Mine : A Ngo")
check("...and the sheet is otherwise clean", got["problems"], [])
got = readiness_import.parse(sheet([("20H01498", "", "BH", DAY, "06:00")], route_col=False), strict=True)
check("a sheet with no Route column says nothing about routes", "route" in got["rows"][0], False)

print("\ndeclared on the page")
sub_c = client("subcontractor")
body = {"date": DAY, "subcontractor_id": SID, "rows": [
    {"plate": "20H01498", "route": "Mine : A Ngo", "activity": "BH", "arrive_date": DAY, "arrive_hhmm": "06:00"},
    {"plate": "20C10615", "route": "a ngo:chan may", "activity": "BH", "arrive_date": DAY, "arrive_hhmm": "06:30"},
    {"plate": "20H01499", "route": "", "activity": "BH", "arrive_date": DAY, "arrive_hhmm": "06:45"}]}
r = sub_c.post("/api/shift/list", json=body)
check("the sheet saves", r.status_code, 200)
check("each row carries the route it named - spelling forgiven",
      row_routes(), {"20H01498": MA, "20C10615": AC, "20H01499": None})
with app.app_context():
    check("the fleet's own routes did not move",
          {t.plate: t.route_id for t in Truck.query.all()},
          {"20H01498": CM, "20C10615": MA, "20H01499": None})
rows = {x["plate"]: x for x in r.get_json()["rows"]}
check("the page shows the declared route", rows["20H01498"]["route"], "Mine : A Ngo")
check("...marked as declared", rows["20H01498"]["route_declared"], True)
check("a blank one shows nothing for a truck with no fleet route",
      (rows["20H01499"]["route"], rows["20H01499"]["route_declared"]), ("", False))

bad = dict(body, rows=[dict(body["rows"][0], route="Mine : Da Nang")])
r = sub_c.post("/api/shift/list", json=bad)
check("a route that does not exist is refused", (r.status_code, r.get_json().get("code")),
      (400, "unknown_route"))
check("...and nothing changed", row_routes()["20H01498"], MA)

print("\na save that does not mention the route keeps it")
adm = client("admin")
r = adm.post("/api/shift/list", json={"date": DAY, "subcontractor_id": SID, "rows": [
    {"plate": p, "ready": True, "state": "approved", "arrive_date": DAY, "arrive": t}
    for p, t in (("20H01498", "06:00"), ("20C10615", "06:30"), ("20H01499", "06:45"))]})
check("the supervisor's board saves ticks and times", r.status_code, 200)
check("the routes are still there", row_routes(), {"20H01498": MA, "20C10615": AC, "20H01499": None})

print("\nwhich route a truck is on, by day")
with app.app_context():
    MINE_ANGO = ("xppl", "loading", "border", "ango")
    check("with no day: the fleet's route", sr._route_paths().get("20H01498"), sr.DEFAULT_PATH)
    check("on the declared day: the declared route", sr._route_paths(DAY).get("20H01498"), MINE_ANGO)
    check("the day before it was declared for: the fleet's", sr._route_paths(TODAY).get("20H01498"),
          sr.DEFAULT_PATH)
    check("the day after, mid-run: still the declared one", sr._route_paths(NEXT).get("20H01498"), MINE_ANGO)
    check("long after: back to the fleet's", sr._route_paths(FAR).get("20H01498"), sr.DEFAULT_PATH)
    check("a truck declared onto A Ngo : Chan May", sr._route_paths(DAY).get("20C10615"),
          ("ango", "ql49", "port"))

print("\nthe plan follows the declaration")
with app.app_context():
    DailyListRow.query.update({"state": "approved"})
    db.session.commit()
    with app.test_request_context():
        data = sr._revision_data(DAY, None)
        week = sr._week_data(DAY, None, True)
    rows = {x["plate"]: x for x in data["rows"]}
    t = rows["20H01498"]["t"]
    check("the corridor truck, declared onto Mine : A Ngo, is planned to A Ngo",
          (rows["20H01498"]["route_name"], t["arrive_ango"] is not None, t["arrive_port"]),
          ("Mine : A Ngo", True, None))
    check("the Mine : A Ngo truck, declared onto A Ngo : Chan May, starts at A Ngo",
          (rows["20C10615"]["route_name"], rows["20C10615"]["start_role"]), ("A Ngo : Chan May", "ango"))
    check("a truck with no route anywhere runs the corridor",
          (rows["20H01499"]["route_name"], rows["20H01499"]["start_role"]), ("", "xppl"))
    wk = [x for x in week["rows"] if x["plate"] == "20H01498"]
    check("the week plans it the same way, every loop",
          sorted({x["route_name"] for x in wk}), ["Mine : A Ngo"])

print("\nthe GPS stamps walk the declared route")
with app.app_context():
    T0 = datetime.strptime(DAY, "%Y-%m-%d") + timedelta(hours=6)
    v = lambda role, h, h2: {"plate": "20H01498", "anchor_id": ROLES[role],
                             "enter": T0 + timedelta(hours=h), "exit": T0 + timedelta(hours=h2),
                             "open": False}
    vs = [v("xppl", 0, 2), v("loading", 0.5, 1.5), v("border", 5, 6), v("ango", 7, 9),
          v("border", 10, 11), v("xppl", 15, 16)]
    actuals.stamp_days([DAY], vs, ROLES)
    db.session.commit()
    got = {(s.leg, s.role, s.edge): s.at for s in ActualStamp.query.filter_by(day=DAY, key="20H01498").all()}
    check("at A Ngo is stamped - the declared route ends there", got.get(("fh", "ango", "enter")),
          T0 + timedelta(hours=7))
    check("the border on the way home is stamped", got.get(("bh", "border", "enter")),
          T0 + timedelta(hours=10))
    check("nothing at a port this run never goes to", ("fh", "port", "enter") in got, False)

print("\nthe Monitor shows the day's route")
with app.app_context():
    with app.test_request_context():
        data = sr._revision_data(DAY, None)
    db.session.add(PlanSnapshot(week_start=DAY, day=DAY, subcontractor_id=None, issued_by="t",
                                rows=data["rows"], figures=[]))
    db.session.commit()
tr = {x["plate"]: x for x in client("monitor").get("/api/shift/track?date=" + DAY).get_json()["rows"]}
check("the truck sits under the declared route", tr["20H01498"]["route_name"], "Mine : A Ngo")
port = [c for c in tr["20H01498"]["fh"] if c["key"] == "port"]
check("...and the port is off its route", bool(port and port[0].get("na")), True)
check("the other truck under its own", tr["20C10615"]["route_name"], "A Ngo : Chan May")


def upload(path, **form):
    data = dict({"date": DAY, "subcontractor_id": str(SID)}, **form)
    with open(path, "rb") as f:
        data["file"] = (io.BytesIO(f.read()), "readiness.xlsx")
    return sub_c.post("/api/shift/upload", data=data, content_type="multipart/form-data")


print("\ndeclared on the uploaded sheet")
with app.app_context():
    # Back to a sheet still being filled in: a confirmed list takes no upload.
    dl = DailyList.query.first()
    dl.state = "draft"
    DailyListRow.query.update({"state": "pending"})
    db.session.commit()
r = upload(sheet([("20H01498", "A Ngo : Chan May", "BH", DAY, "06:00"),
                  ("20C10615", "Mine : A Ngo", "BH", DAY, "06:30")]), replace="1")
check("a sheet with routes imports", r.status_code, 200)
check("the rows now carry the sheet's routes", (row_routes()["20H01498"], row_routes()["20C10615"]), (AC, MA))
r = upload(sheet([("20H01498", "Mine : Hue", "BH", DAY, "06:00")]), replace="1")
j = r.get_json()
check("a route that does not exist refuses the file", (r.status_code, j.get("code")), (400, "invalid"))
check("...naming the column and the truck",
      [(p["column"], p["plate"]) for p in j.get("problems", [])], [("Route", "20H01498")])
r = upload(sheet([("20H01498", "", "BH", DAY, "07:00")], route_col=False), replace="1")
check("a sheet with no Route column imports", r.status_code, 200)
check("...and leaves the declared route as it was", row_routes()["20H01498"], AC)
r = upload(sheet([("20H01498", "", "BH", DAY, "07:00")]), replace="1")
check("a blank Route cell puts the truck back on its fleet route",
      (r.status_code, row_routes()["20H01498"]), (200, None))
check("...and the import report says so",
      any("no Route" in w for w in r.get_json().get("warnings", [])), True)

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
