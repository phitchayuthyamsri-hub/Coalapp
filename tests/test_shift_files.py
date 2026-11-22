# -*- coding: utf-8 -*-
"""A truck can be declared more than once on a day's sheet: a second trip.

Run: python tests/test_shift_files.py   (PYTHONIOENCODING=utf-8 on Windows)

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




sr.SHIFT_MODE_FROM = "2000-01-01"       # every day here runs on AM / PM files
from app.models import DailyList, PlanSnapshot   # noqa: E402,F811

TODAY_ = (datetime.utcnow() + sr.LOCAL_OFFSET).strftime("%Y-%m-%d")


def rows_of(plate=None):
    with app.app_context():
        out = sorted((r.plate, r.shift, sr._trip_no(r), r.arrive_date, r.arrive_hhmm, r.note, r.state)
                     for r in DailyListRow.query.join(DailyList, DailyList.id == DailyListRow.list_id)
                     .filter(DailyList.list_date == DAY).all())
    return [x for x in out if plate is None or x[0] == plate]


print("which shift a time is in")
with app.app_context():
    check("06:00 is AM", sr._shift_of(DAY, DAY, "06:00"), "AM")
    check("17:59 is AM", sr._shift_of(DAY, DAY, "17:59"), "AM")
    check("18:00 is PM", sr._shift_of(DAY, DAY, "18:00"), "PM")
    check("05:59 the next morning is still the day's PM", sr._shift_of(DAY, NEXT, "05:59"), "PM")
    check("06:00 the next morning is the next day", sr._shift_of(DAY, NEXT, "06:00"), None)
    check("05:00 on the day is the day before's PM", sr._shift_of(DAY, DAY, "05:00"), None)

sub_c = client("subcontractor")


def save(shift, rows, who=None, day=None):
    c = who or sub_c
    body = {"date": day or DAY, "subcontractor_id": SID, "rows": rows}
    if shift:
        body["shift"] = shift
    r = c.post("/api/shift/list", json=body)
    return r.status_code, (r.get_json() or {})


T = lambda plate, d, t, st="BH", route="Mine : A Ngo": {
    "plate": plate, "route": route, "activity": st, "arrive_date": d, "arrive_hhmm": t}

print("\nthe AM declaration")
code, j = save(None, [T("20C10615", DAY, "08:00")])
check("a company save without AM / PM is refused", (code, j.get("code")), (400, "need_shift"))
code, j = save("AM", [T("20C10615", DAY, "08:00"), T("20H01498", DAY, "10:00", route="Mine : Chan May"),
                      {"plate": "20H01499", "activity": "Maintenance"}])
check("the AM declaration saves", code, 200)
check("...each truck in AM", rows_of(), [
    ("20C10615", "AM", 1, DAY, "08:00", "BH", "pending"),
    ("20H01498", "AM", 1, DAY, "10:00", "BH", "pending"),
    ("20H01499", "AM", 1, "", "", "Maintenance", "pending")])
check("the page gets the shift timetable", [s["shift"] for s in j.get("shifts", [])], ["AM", "PM"])
check("...with the company deadline the day before at 14:00",
      j["shifts"][0]["steps"][0]["due"], (datetime.strptime(DAY, "%Y-%m-%d") - timedelta(days=1)).strftime("%d/%m") + " 14:00")
check("...and PM's on the day at 09:00", j["shifts"][1]["steps"][0]["due"],
      datetime.strptime(DAY, "%Y-%m-%d").strftime("%d/%m") + " 09:00")

print("\nthe PM declaration adds, it does not replace")
code, j = save("PM", [T("20C10615", NEXT, "02:00"), {"plate": "20H01498", "activity": "FH",
                                                     "route": "Mine : Chan May"}])
check("the PM declaration saves", code, 200)
check("20C10615: AM 08:00 kept, PM 02:00 added as trip 2", rows_of("20C10615"), [
    ("20C10615", "AM", 1, DAY, "08:00", "BH", "pending"),
    ("20C10615", "PM", 2, NEXT, "02:00", "BH", "pending")])
check("20H01498 named in PM with no time: its AM trip stands", rows_of("20H01498"),
      [("20H01498", "AM", 1, DAY, "10:00", "BH", "pending")])
check("a truck the PM declaration does not name is untouched", rows_of("20H01499")[0][5], "Maintenance")
code, j = save("PM", [T("20C10615", NEXT, "03:00")])
check("the same truck again in PM at another time", code, 200)
check("...moves its PM trip, never adds a third", rows_of("20C10615"), [
    ("20C10615", "AM", 1, DAY, "08:00", "BH", "pending"),
    ("20C10615", "PM", 2, NEXT, "03:00", "BH", "pending")])

print("\nwhat a declaration refuses")
code, j = save("PM", [T("20H01499", DAY, "09:00")])
check("an AM time in the PM declaration", (code, j.get("code")), (400, "shift"))
check("...says which file it belongs in", "belongs in the AM file" in j.get("error", ""), True)
code, j = save("AM", [T("20C10615", DAY, "08:00"), T("20C10615", DAY, "11:00")])
check("a truck twice in one declaration", (code, "twice" in j.get("error", "")), (400, True))
code, j = save("AM", [T("20H01499", DAY, "05:00")])
check("05:00 on the day (the day before's PM)", (code, "outside this day" in j.get("error", "")), (400, True))
code, j = save("AM", [{"plate": "20H01499", "activity": "BH", "arrive_date": DAY}])
check("a date with no time", code, 400)
check("...and nothing changed", rows_of("20H01499")[0][3:6], ("", "", "Maintenance"))

print("\na trip already sent on is protected")
with app.app_context():
    for x in DailyListRow.query.filter_by(key="20C10615").all():
        if x.shift == "AM":
            x.state = "approved"
    db.session.commit()
    stamp0 = DailyListRow.query.filter_by(key="20C10615", shift="AM").first().declared_at
code, j = save("AM", [T("20C10615", DAY, "09:00")])
check("moving an approved AM trip from the company page", (code, "Request to amend" in j.get("error", "")),
      (400, True))
code, j = save("AM", [dict(T("20C10615", DAY, "08:00"), remark="driver changed")])
check("sending it again unchanged is fine", code, 200)
with app.app_context():
    x = DailyListRow.query.filter_by(key="20C10615", shift="AM").first()
    check("...state kept, remark refreshed, declared time not reset",
          (x.state, x.remark, x.declared_at == stamp0), ("approved", "driver changed", True))

print("\nthe supervisor's board on an AM / PM day")
adm = client("admin")
board = [{"plate": "20C10615", "ready": True, "arrive_date": DAY, "arrive": "08:00", "activity": "BH"},
         {"plate": "20C10615", "ready": True, "arrive_date": NEXT, "arrive": "03:00", "activity": "BH"},
         {"plate": "20H01498", "ready": True, "arrive_date": DAY, "arrive": "10:00", "activity": "BH"},
         {"plate": "20H01499", "ready": False, "activity": "Maintenance", "reason": "Maintenance"}]
code, j = save(None, board, who=adm)
check("the board saves the whole sheet", code, 200)
check("states kept per shift", [x[6] for x in rows_of("20C10615")], ["approved", "pending"])
code, j = save(None, board + [{"plate": "20H01498", "ready": True, "arrive_date": DAY, "arrive": "16:00",
                               "activity": "BH"}], who=adm)
check("a second AM trip from the board is refused", (code, "18:00 or later" in j.get("error", "")), (400, True))
code, j = save(None, board + [{"plate": "20H01498", "ready": True, "arrive_date": DAY, "arrive": "21:00",
                               "activity": "BH"}], who=adm)
check("a PM trip added on the board", code, 200)
check("...is trip 2 in PM, pending", rows_of("20H01498")[1], ("20H01498", "PM", 2, DAY, "21:00", "BH", "pending"))

print("\nthe Excel files")


def upload(path, shift=None, day=None):
    data = {"date": day or DAY, "subcontractor_id": str(SID)}
    if shift:
        data["shift"] = shift
    with open(path, "rb") as f:
        data["file"] = (io.BytesIO(f.read()), "readiness.xlsx")
    r = sub_c.post("/api/shift/upload", data=data, content_type="multipart/form-data")
    return r.status_code, (r.get_json() or {})


code, j = upload(sheet([("20H01499", "Mine : A Ngo", "BH", DAY, "07:00")]))
check("a file without AM / PM is refused", (code, j.get("code")), (400, "need_shift"))
code, j = upload(sheet([("20H01499", "Mine : A Ngo", "BH", DAY, "07:00")]), "AM")
check("the AM file goes in", code, 200)
check("...its Maintenance row becomes its AM trip", rows_of("20H01499"),
      [("20H01499", "AM", 1, DAY, "07:00", "BH", "pending")])
code, j = upload(sheet([("20H01499", "Mine : A Ngo", "BH", NEXT, "01:00"),
                        ("20C10615", "Mine : A Ngo", "BH", NEXT, "03:00")]), "PM")
check("the PM file goes in after the AM one is approved", code, 200)
check("...adding 20H01499's second trip", rows_of("20H01499")[1], ("20H01499", "PM", 2, NEXT, "01:00", "BH", "pending"))
check("...the AM file's rows untouched", rows_of("20H01499")[0][1:5], ("AM", 1, DAY, "07:00"))
code, j = upload(sheet([("20H01499", "Mine : A Ngo", "BH", DAY, "12:00")]), "PM")
check("an AM time in the PM file is refused", (code, j.get("code")), (400, "shift"))

print("\nwhich sheet a company may send")
code, j = save("AM", [], day=TODAY_)
check("AM for today: too late, refused", (code, j.get("code")), (400, "not_tomorrow"))
code, j = save("PM", [], day=TODAY_)
check("PM for today: the PM file is sent on the day", code, 200)

print("\nlate")
with app.app_context():
    x = DailyListRow.query.filter_by(key="20H01499", shift="AM").first()
    due = sr._step_due(DAY, "AM", "company")
    x.declared_at = due - sr.LOCAL_OFFSET - timedelta(minutes=1)
    check("sent before the AM deadline", sr._is_late(x, DAY), False)
    x.declared_at = due - sr.LOCAL_OFFSET + timedelta(minutes=1)
    check("sent a minute after it: late", sr._is_late(x, DAY), True)
    db.session.commit()
r = adm.get("/api/shift/list?date=%s&subcontractor_id=%s" % (DAY, SID))
lj = r.get_json()
check("the page marks the row late", [x["late"] for x in lj["rows"] if x["plate"] == "20H01499" and x["shift"] == "AM"],
      [True])
check("...and the AM shift names it", lj["shifts"][0]["late"], ["20H01499"])

print("\nthe plan, by shift")
with app.app_context():
    DailyListRow.query.update({"state": "approved"})
    db.session.commit()
    with app.test_request_context():
        whole = sr._revision_data(DAY, None)
        am = sr._revision_data(DAY, None, "AM")
        pm = sr._revision_data(DAY, None, "PM")
        nxt = sr._revision_data(NEXT, None)
    key = lambda d: sorted((x["plate"], x.get("shift"), x["loop"], x["day"], x["t"]["arrive_mine"]) for x in d["rows"])
    check("the AM plan", key(am), [
        ("20C10615", "AM", 1, DAY, DAY + "T08:00"), ("20H01498", "AM", 1, DAY, DAY + "T10:00"),
        ("20H01499", "AM", 1, DAY, DAY + "T07:00")])
    check("the PM plan: after-midnight runs are this day's, Loop 2", key(pm), [
        ("20C10615", "PM", 2, DAY, NEXT + "T03:00"), ("20H01498", "PM", 2, DAY, DAY + "T21:00"),
        ("20H01499", "PM", 2, DAY, NEXT + "T01:00")])
    check("the whole day is both", len(whole["rows"]), 6)
    check("the next day does not take this day's PM", [x["plate"] for x in nxt["rows"]], [])

print("\nissued shift by shift")
r = adm.post("/api/shift/revision/issue", json={"date": DAY})
check("issuing with no shift is refused", (r.status_code, (r.get_json() or {}).get("code")), (400, "need_shift"))
r = adm.post("/api/shift/revision/issue", json={"date": DAY, "shift": "AM"})
check("AM issued", r.status_code, 200)
r = adm.post("/api/shift/revision/issue", json={"date": DAY, "shift": "AM"})
check("AM again asks first", (r.status_code, (r.get_json() or {}).get("reissue_needed")), (409, True))
r = adm.post("/api/shift/revision/issue", json={"date": DAY, "shift": "PM"})
check("PM issued", r.status_code, 200)
with app.app_context():
    snap = sr._issued_for(DAY, None)
    check("the plan in force holds both shifts", sorted({x.get("shift") for x in snap.rows}), ["AM", "PM"])
    check("...six runs", len(snap.rows), 6)
    check("...marked as the PM issue", snap.shift, "PM")
    plan = tool_link._plan(None)
    check("Daily page: a truck's AM trip on its date", plan.get("20H01499|" + DAY, {}).get("mineArrive"),
          DAY + "T07:00")
    check("Daily page: its after-midnight PM trip on the date it arrives",
          plan.get("20H01499|" + NEXT, {}).get("mineArrive"), NEXT + "T01:00")
    check("Daily page: a same-date PM trip leaves the AM one in place",
          plan.get("20H01498|" + DAY, {}).get("mineArrive"), DAY + "T10:00")
    with app.test_request_context():
        wb = sr._revision_workbook(DAY, None, "adm", "PM")
    from openpyxl import load_workbook
    ws = load_workbook(io.BytesIO(wb)).active
    check("the PM workbook says so in its title", "PM shift" in ws["A1"].value, True)

print()
print("ALL PASS" if not FAIL else "%d FAILED" % FAIL)
sys.exit(1 if FAIL else 0)
