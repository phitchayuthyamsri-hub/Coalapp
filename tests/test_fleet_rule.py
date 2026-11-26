# -*- coding: utf-8 -*-
"""Only trucks in the company's fleet can be declared (26/11/2026).

Run: python tests/test_fleet_rule.py   (PYTHONIOENCODING=utf-8 on Windows)

"From now on please denied the declare of truck that is not in the fleet, set a
remark as pop-up on both Eng and Vietnam". Bac Nam declared 55 trucks against
a fleet of 50 and all 55 were planned. A declared truck that is not active in
the company's fleet on the sheet's day is marked Denied (never planned), the
rest of the sheet saves, the page is told which trucks, and a truck put back
in the fleet is reopened on the next save.
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




sr.SHIFT_MODE_FROM = "2000-01-01"
sr.FLEET_RULE_FROM = "2000-01-01"
from app.models import DailyList   # noqa: E402,F811

with app.app_context():
    # The company's fleet: 20H01498 and 20C10615 active; 20H01499 deactivated; 20H09999 not in the fleet.
    for t in Truck.query.all():
        t.subcontractor_id = SID
        if t.plate == "20H01499":
            t.status = "deactivated"
    db.session.commit()


def rows_of():
    with app.app_context():
        dl = DailyList.query.filter_by(list_date=DAY).first()
        return sorted((r.plate, r.state, r.reason) for r in DailyListRow.query.filter_by(list_id=dl.id).all())


sub_c = client("subcontractor")
T = lambda plate, t: {"plate": plate, "route": "Mine : A Ngo", "activity": "BH", "arrive_date": DAY, "arrive_hhmm": t}
print("declaring trucks that are not in the fleet")
r = sub_c.post("/api/shift/list", json={"date": DAY, "subcontractor_id": SID, "shift": "AM", "rows": [
    T("20H01498", "08:00"), T("20H01499", "09:00"), T("20H09999", "10:00")]})
j = r.get_json() or {}
check("the sheet saves - the rest is not held up", r.status_code, 200)
check("the page is told which trucks were not accepted", j.get("fleet_denied"), ["20H01499", "20H09999"])
check("deactivated and unknown trucks are Denied with the reason, the fleet truck is not", rows_of(), [
    ("20H01498", "pending", ""), ("20H01499", "denied", sr.FLEET_DENY), ("20H09999", "denied", sr.FLEET_DENY)])
with app.app_context():
    check("a sheet with only rule-denied rows besides pending ones still reads draft",
          DailyList.query.filter_by(list_date=DAY).first().state, "draft")
    with app.test_request_context():
        plan = sr._revision_data(DAY, None)
    check("denied trucks are not planned", sorted(x["plate"] for x in plan["rows"]), ["20H01498"])

print("\nsending the file again with a new time for a denied truck")
r = sub_c.post("/api/shift/list", json={"date": DAY, "subcontractor_id": SID, "shift": "AM", "rows": [
    T("20H01498", "08:00"), T("20H09999", "11:00")]})
check("not refused as 'already decided'", (r.status_code, (r.get_json() or {}).get("fleet_denied")), (200, ["20H01499", "20H09999"]))

print("\nthe truck is put back in the fleet")
with app.app_context():
    t = Truck.query.filter_by(plate="20H01499").first()
    t.status = "online"
    db.session.commit()
r = sub_c.post("/api/shift/list", json={"date": DAY, "subcontractor_id": SID, "shift": "AM", "rows": [T("20H01498", "08:00")]})
check("the next save reopens it", [x for x in rows_of() if x[0] == "20H01499"], [("20H01499", "pending", "")])
check("...and only the truck still outside the fleet is reported", (r.get_json() or {}).get("fleet_denied"), ["20H09999"])

print("\na truck outside its fleet dates")
with app.app_context():
    t = Truck.query.filter_by(plate="20C10615").first()
    t.eff_to = (datetime.strptime(DAY, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    db.session.commit()
r = sub_c.post("/api/shift/list", json={"date": DAY, "subcontractor_id": SID, "shift": "AM", "rows": [T("20C10615", "12:00")]})
check("left the fleet before the sheet's day: denied", (r.get_json() or {}).get("fleet_denied"), ["20C10615", "20H09999"])

print("\nthe supervisor's submit")
with app.app_context():
    dl = DailyList.query.filter_by(list_date=DAY).first()
    x = DailyListRow.query.filter_by(list_id=dl.id, key="20H09999").first()
    x.state, x.reason, x.ready = "pending", "", True          # as a sheet saved before the rule would hold it
    db.session.commit()
adm = client("admin")
r = adm.post("/api/shift/list/submit", json={"date": DAY, "subcontractor_id": SID})
check("submit goes through", r.status_code, 200)
check("a truck outside the fleet is denied at submit, never sent to the manager",
      [x[1] for x in rows_of() if x[0] == "20H09999"], ["denied"])
check("the fleet trucks went to the manager", sorted(x[0] for x in rows_of() if x[1] == "applied"),
      ["20H01498", "20H01499"])
with open(os.path.join(HERE, "..", "app", "templates", "subcontractor.html"), encoding="utf-8") as f:
    page = f.read()
check("the company page has the pop-up in English and Vietnamese",
      ("NOT ACCEPTED" in page, "KHÔNG ĐƯỢC CHẤP NHẬN" in page, "fleetDeniedPopup(j.fleet_denied)" in page), (True, True, True))
with open(os.path.join(HERE, "..", "app", "templates", "shift_board.html"), encoding="utf-8") as f:
    board = f.read()
check("...and the supervisor's page", "fleetDeniedPopup(r.data && r.data.fleet_denied)" in board, True)

print()
print("ALL PASS" if not FAIL else "%d FAILED" % FAIL)
sys.exit(1 if FAIL else 0)
