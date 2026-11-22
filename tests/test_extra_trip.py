# -*- coding: utf-8 -*-
"""A truck can be declared more than once on a day's sheet: a second trip.

Run: python tests/test_extra_trip.py   (PYTHONIOENCODING=utf-8 on Windows)

21/11/2026, "truck with routing Mine : A Ngo has short running time ... please
help make plan can be resubmitted again in the same day but different time".
One row per truck per sheet meant a truck back at the mine within the day could
only go on the next day's sheet, and waited for that plan. Now a sheet can name
the truck again at a later time - trip 2 - and that trip is in the sheet's own
day's plan, even when it reaches the mine after midnight (22/11 03:00 in the
21/11 plan).
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
from app import actuals, readiness_import, tool_link                         # noqa: E402
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
from app import shift_routes as _sr_pin   # noqa: E402
_sr_pin.SHIFT_MODE_FROM = "2099-01-01"   # one-file sheets; AM / PM files: test_shift_files.py
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




def trips(plate=None):
    with app.app_context():
        out = sorted((r.plate, sr._trip_no(r), r.arrive_date, r.arrive_hhmm, r.state)
                     for r in DailyListRow.query.all())
    return [x for x in out if plate is None or x[0] == plate]


AFTER = (datetime.strptime(NEXT, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

print("the sheet file: the same truck twice")
got = readiness_import.parse(sheet([("20C10615", "Mine : A Ngo", "BH", DAY, "06:00"),
                                    ("20C10615", "Mine : A Ngo", "BH", NEXT, "03:00")]), strict=True)
check("at different times: two rows, two trips", len(got["rows"]), 2)
check("...said so", any("2 trips" in w for w in got["warnings"]), True)
got = readiness_import.parse(sheet([("20C10615", "Mine : A Ngo", "BH", DAY, "06:00"),
                                    ("20C10615", "Mine : A Ngo", "FH", DAY, "06:00")]), strict=True)
check("at the same time: a repeat, the later row used",
      [(r["activity"], r["arrive_time"]) for r in got["rows"]], [("FH", "06:00")])
got = readiness_import.parse(sheet([("20C10615", "Mine : A Ngo", "BH", DAY, "06:00"),
                                    ("20C10615", "Mine : A Ngo", "BH", "", "")]), strict=True)
check("a repeat with no time: the later row used", len(got["rows"]), 1)

print("\ndeclared on the page")
sub_c = client("subcontractor")
r = sub_c.post("/api/shift/list", json={"date": DAY, "subcontractor_id": SID, "rows": [
    {"plate": "20C10615", "route": "Mine : A Ngo", "activity": "BH", "arrive_date": NEXT, "arrive_hhmm": "03:00"},
    {"plate": "20C10615", "route": "Mine : A Ngo", "activity": "BH", "arrive_date": DAY, "arrive_hhmm": "06:00"},
    {"plate": "20H01498", "route": "Mine : Chan May", "activity": "BH", "arrive_date": DAY, "arrive_hhmm": "07:00"}]})
check("a truck twice saves", r.status_code, 200)
check("trips numbered by time at the mine, whatever order they came in", trips("20C10615"),
      [("20C10615", 1, DAY, "06:00", "pending"), ("20C10615", 2, NEXT, "03:00", "pending")])
pay = [(x["plate"], x["trip"], x["arrive"]) for x in r.get_json()["rows"] if not x.get("absent")]
check("the page gets both rows back, with their trip", sorted(pay),
      [("20C10615", 1, "06:00"), ("20C10615", 2, "03:00"), ("20H01498", 1, "07:00")])


def refused(rows):
    r = sub_c.post("/api/shift/list", json={"date": DAY, "subcontractor_id": SID, "rows": rows})
    return r.status_code, (r.get_json() or {}).get("code")


one = {"plate": "20C10615", "route": "Mine : A Ngo", "activity": "BH", "arrive_date": DAY, "arrive_hhmm": "06:00"}
check("a second trip with no time is refused",
      refused([one, dict(one, arrive_hhmm="")]), (400, "trips"))
check("two trips at the same time are refused", refused([one, dict(one)]), (400, "trips"))
check("a second trip two days on is refused",
      refused([one, dict(one, arrive_date=AFTER, arrive_hhmm="03:00")]), (400, "trips"))
check("a second trip on a truck not running is refused",
      refused([one, dict(one, activity="Maintenance", arrive_hhmm="20:00")]), (400, "trips"))
check("...and the sheet is as it was", len(trips("20C10615")), 2)
check("a second trip the same evening is fine",
      refused([one, dict(one, arrive_hhmm="20:00")]), (200, None))
check("...replacing the 03:00 one", trips("20C10615")[1][2:4], (DAY, "20:00"))

print("\nthe board: states are kept per trip")
with app.app_context():
    for x in DailyListRow.query.all():
        x.state = "approved" if sr._trip_no(x) == 1 else "pending"
    db.session.commit()
adm = client("admin")
board = [{"plate": "20C10615", "trip": 1, "ready": True, "arrive_date": DAY, "arrive": "06:00", "activity": "BH"},
         {"plate": "20C10615", "trip": 2, "ready": True, "arrive_date": DAY, "arrive": "20:00", "activity": "BH"},
         {"plate": "20H01498", "trip": 1, "ready": True, "arrive_date": DAY, "arrive": "07:00", "activity": "BH"}]
r = adm.post("/api/shift/list", json={"date": DAY, "subcontractor_id": SID, "rows": board})
check("the board saves both trips", r.status_code, 200)
check("each trip keeps its own state", [x[4] for x in trips("20C10615")], ["approved", "pending"])
with app.app_context():
    DailyListRow.query.filter_by(key="20H01498").update({"state": "approved"})
    db.session.commit()
r = adm.post("/api/shift/list", json={"date": DAY, "subcontractor_id": SID, "rows": board + [
    {"plate": "20H01498", "trip": 2, "ready": True, "arrive_date": NEXT, "arrive": "02:00", "activity": "BH"}]})
check("a trip added to an approved truck", r.status_code, 200)
check("...takes the truck's state", trips("20H01498")[1][1:], (2, NEXT, "02:00", "approved"))
r = adm.post("/api/shift/list", json={"date": DAY, "subcontractor_id": SID, "rows": board})
check("leaving a trip out removes it", len(trips("20H01498")), 1)
with app.app_context():
    check("a route declared on the page is kept by the board's save",
          {x.route_id for x in DailyListRow.query.filter_by(key="20C10615").all()}, {MA})

print("\nthe plan for the day")
r = adm.post("/api/shift/list", json={"date": DAY, "subcontractor_id": SID, "rows": [
    dict(board[0]), dict(board[1], arrive_date=NEXT, arrive="03:00"), dict(board[2])]})
check("the after-midnight trip saves", r.status_code, 200)
with app.app_context():
    with app.test_request_context():
        d1 = sr._revision_data(DAY, None)
        d2 = sr._revision_data(NEXT, None)
    mine = [(x["plate"], x.get("trip", 1), x["loop"], x["day"], x["t"]["arrive_mine"])
            for x in d1["rows"] if x["plate"] == "20C10615"]
    check("both trips are in the sheet's day's plan", mine,
          [("20C10615", 1, 1, DAY, DAY + "T06:00"), ("20C10615", 2, 2, DAY, NEXT + "T03:00")])
    check("the second trip is not in the next day's plan as well",
          [x["plate"] for x in d2["rows"]], [])
    check("the next day is not counted as having it", d1["elsewhere"], [])
    with app.test_request_context():
        wb = sr._revision_workbook(DAY, None, "adm")
    from openpyxl import load_workbook
    ws = load_workbook(io.BytesIO(wb)).active
    loops = [(ws.cell(i, 2).value, ws.cell(i, 3).value) for i in range(1, ws.max_row + 1)
             if ws.cell(i, 2).value == "20C10615"]
    check("the workbook shows Loop 1 and Loop 2", loops, [("20C10615", 1), ("20C10615", 2)])

    print("\nthe Daily page")
    db.session.add(PlanSnapshot(week_start=DAY, day=DAY, rows=d1["rows"]))
    db.session.commit()
    plan = tool_link._plan(None)
    check("trip 1 under its own date", plan.get("20C10615|" + DAY, {}).get("mineArrive"), DAY + "T06:00")
    check("trip 2 under the date it reaches the mine", plan.get("20C10615|" + NEXT, {}).get("mineArrive"),
          NEXT + "T03:00")
    rows2 = [dict(x) for x in d1["rows"]]
    for x in rows2:
        if x.get("trip") == 2:
            x["t"] = dict(x["t"], arrive_mine=DAY + "T20:00")
    db.session.add(PlanSnapshot(week_start=DAY, day=DAY, rows=rows2))
    db.session.commit()
    plan = tool_link._plan(None)
    check("a trip 2 on the same date leaves trip 1 in place",
          plan.get("20C10615|" + DAY, {}).get("mineArrive"), DAY + "T06:00")
    st = tool_link._status(None)
    check("the declared-status grid has the truck once, on its first trip's day",
          sorted(st["cell"]["20C10615"].keys()), [DAY])

print("\nthe uploaded sheet")
with app.app_context():
    dl = DailyList.query.filter_by(list_date=DAY).first()
    dl.state = "draft"
    DailyListRow.query.update({"state": "pending"})
    db.session.commit()


def upload(path, **form):
    data = dict({"date": DAY, "subcontractor_id": str(SID)}, **form)
    with open(path, "rb") as f:
        data["file"] = (io.BytesIO(f.read()), "readiness.xlsx")
    return sub_c.post("/api/shift/upload", data=data, content_type="multipart/form-data")


r = upload(sheet([("20C10615", "Mine : A Ngo", "BH", DAY, "06:00"),
                  ("20C10615", "Mine : A Ngo", "BH", DAY, "19:30")]), replace="1")
check("a file with the truck twice uploads", r.status_code, 200)
check("...as two trips", [x[1:4] for x in trips("20C10615")], [(1, DAY, "06:00"), (2, DAY, "19:30")])
check("a truck the file does not name is left alone", len(trips("20H01498")), 1)
r = upload(sheet([("20C10615", "Mine : A Ngo", "BH", DAY, "06:15")]), replace="1")
check("a file naming it once replaces both trips", [x[1:4] for x in trips("20C10615")], [(1, DAY, "06:15")])
r = upload(sheet([("20C10615", "Mine : A Ngo", "BH", DAY, "06:00"),
                  ("20C10615", "Mine : A Ngo", "BH", AFTER, "03:00")]), replace="1")
check("a file with a second trip two days on is refused", (r.status_code, (r.get_json() or {}).get("code")),
      (400, "trips"))

print()
print("ALL PASS" if not FAIL else "%d FAILED" % FAIL)
sys.exit(1 if FAIL else 0)
