# -*- coding: utf-8 -*-
"""Daily/Weekly performance report: the three data lists (11/11/2026).

Run: python tests/test_coal_report.py   (PYTHONIOENCODING=utf-8 on Windows)

1 Input_Actual data loading, 2 Truck readiness and 3 Contract are filled from
the team's Calculation file (sheets by those names; Contract's headers on
row 3; "Transportion Company") or from the daily exports. A file replaces the
days it covers and keeps the others.
"""
import io
import os
import sys
import tempfile
from datetime import datetime, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

_tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL="sqlite:///" + os.path.join(_tmp, "t.db").replace("\\", "/"),
    SECRET_KEY="test-only-not-a-real-key", COALAPP_ENV="")

import openpyxl                                                   # noqa: E402
from app import create_app                                        # noqa: E402
from app.models import db, User, CoalRptWeigh, CoalRptReady       # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(66) + ("" if ok else "got %r want %r" % (got, want)))


W_HDR = ["No.", "W.ID", "Weighing Type", "TicketID", "Truck No", "Date In", "Time In", "Date Out", "Time Out",
         "Weight In", "Weight Out", "Net Weight", "Product Name", "CoalSource", "ProductionCode", "Customer Name",
         "DriverName", "Id/Passport", "CargoLotNo", "CargoName", "CargoCompany", "PackUnit", "PackQtt", "OrderNo",
         "ContractNo", "InvoiceNo", "CoNo", "OVS_DMT"]


def wrow(tid, plate, day, tout, net, contract, mkt):
    d = datetime.strptime(day, "%Y-%m-%d")
    r = [1, tid[3:], "Order Weighing", tid, plate, d, "07:13:00", d, tout, 20000, 20000 + net, net, "Gar", "", "",
         "Namtien Limited Liability Co", "", "", "", "", "", "", 0, contract + "_1", contract, "", "", mkt]
    return r


def calc_file():
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "Input_Actual data loading"
    ws.append(W_HDR)
    ws.append(wrow("W05000001", "73H-031.59", "2026-11-09", "09:10:00", 59940, "Coal Offtake Agreement 291-PO8", "Oversea"))
    ws.append(wrow("W05000002", "73H-031.59", "2026-11-10", "20:30:00", 60120, "Coal Offtake Agreement 291-PO8", "Oversea"))
    ws.append(wrow("W05000003", "ບກ2369", "2026-11-10", "08:00:00", 33190, "151Coal/KCL-XPPL/2026", "Domestic"))
    # out at 02:38: the team's loading day starts 06:00, so this is 09/11 PM
    ws.append(wrow("W05000005", "ບກ2370", "2026-11-10", "02:38:00", 37500, "151Coal/KCL-XPPL/2026", "Domestic"))
    # a broken Date Out falls back to Date In (the file has 1900-01-05 in places)
    bad = wrow("W05000004", "20H-045.06", "2026-11-10", "10:00:00", 43790, "Coal Offtake Agreement 291-PO8", "Oversea")
    bad[7] = datetime(1900, 1, 5)
    ws.append(bad)
    rs = wb.create_sheet("Truck readiness")
    rs.append(["ID", "Register Date", "Contract No", "Truck Plate", "Country", "Wheel", "Trailer Plate", "Truck weight",
               "Pay load", "Container No1", "Container No2", "Driver Name", "ID/Passport", "Phone number",
               "Destination EST", "Transportion Company", "Subcontractor", "Vehicle Status", "Registration Status"])
    rs.append(["a-1", "10/11/2026", "Coal Offtake Agreement 291-PO8", "73H-031.59", "Vietnam", 22, "", 21, 42, "", "", "X", "", "", "CHAN MAY", "PTS", "PTS-VTPL", "RO", "Approved"])
    rs.append(["a-2", "10/11/2026", "Coal Offtake Agreement 291-PO8", "74H-019.66", "Vietnam", 22, "", 21, 42, "", "", "Y", "", "", "CHAN MAY", "PTS", "PTS-VTPL", "RO", "Approved"])
    rs.append(["a-3", "09/11/2026", "151Coal/KCL-XPPL/2026", "ບກ2369", "Laos", 22, "", 21, 42, "", "", "Z", "", "", "", "KCL", "SCGL", "RO", "Approved"])
    cs = wb.create_sheet("Contract")
    cs.append(["Today 11-Nov-26", datetime(2026, 11, 11)])
    cs.append([None] * 13 + ["Original"])
    cs.append(["Customer name", "Customer name full", "Export", "Term", "End User", "Contract#", "Start", "End",
               "Extension", "Gar Type", "Transporter", "Cnt. QTY", "Ton/trp", "Cnt. date", "Tot trip", "Vol./day",
               "Trp/day", "Cnt. to date", "Rmn. Ton", "Rmn. Day", "Vol/day", "Tot. trp req ", "Trp./day", "Status"])
    cs.append(["Namtien", "Namtien Limited Liability Company", "Oversea", "EXW", "N/A", "Coal Offtake Agreement 291-PO8",
               datetime(2026, 10, 25), datetime(2026, 12, 25), None, "FC 5000 Kcal", "NT", 300000, 60] + [0] * 10 + ["Ongoing"])
    cs.append(["Khammouane", "Khammouane Cement Co.,Ltd", "Domestic", "EXW", "N/A", "151Coal/KCL-XPPL/2026",
               datetime(2026, 11, 1), datetime(2027, 1, 31), datetime(2027, 2, 28), "FC 4600 Kcal", "KCL", 20000, 32] + [0] * 10 + ["Ongoing"])
    cs.append([None] * 24)
    b = io.BytesIO(); wb.save(b); b.seek(0)
    return b


def export_ready(day, rows):
    """The daily Registration Trucklist export: sheet 'Data', 'Transport Company'."""
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Data"
    ws.append(["ID", "Register Date", "Contract No", "Truck Plate", "Country", "Wheels", "Trailer Plate", "Truck Weight",
               "Payload", "Container 1", "Container 2", "Driver Name", "ID/Passport", "Phone Number", "Destination EST",
               "Transport Company", "Subcontractor", "Vehicle Status", "Registration Status", "Registration Time"])
    for rid, plate in rows:
        ws.append([rid, day, "Coal Offtake Agreement 291-PO8", plate, "Vietnam", 22, "", 21, 42, "", "", "", "", "",
                   "Cảng Chân Mây", "PTS", "PTS-VTPL", "RO", "Approved", day + " 15:09"])
    b = io.BytesIO(); wb.save(b); b.seek(0)
    return b


app = create_app()
with app.app_context():
    adm = User(username="boss", role="admin"); adm.set_password("x" * 12)
    ro = User(username="look", role="user", can_edit=False); ro.set_password("x" * 12)
    db.session.add_all([adm, ro]); db.session.commit()
    ids = {"boss": str(adm.id), "look": str(ro.id)}


def client(name):
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = ids[name]
        s["_fresh"] = True
    return c


boss = client("boss")
print("\nThe Calculation file fills all three lists")
r = boss.post("/api/coalrpt/upload?kind=all", data={"file": (calc_file(), "1 Calculation file - 20261110.xlsx")},
              content_type="multipart/form-data")
j = r.get_json()
check("uploaded", (r.status_code, j.get("ok")), (200, True))
check("1 Input_Actual data loading: 5 tickets, 09/11 -> 10/11", (j["done"]["weigh"]["rows"], j["done"]["weigh"]["from"], j["done"]["weigh"]["to"]), (5, "2026-11-09", "2026-11-10"))
check("2 Truck readiness: 3 registrations", j["done"]["ready"]["rows"], 3)
check("3 Contract: headers found on row 3, blank row skipped", j["done"]["contracts"]["rows"], 2)
with app.app_context():
    t = db.session.get(CoalRptWeigh, "W05000002")
    w5 = db.session.get(CoalRptWeigh, "W05000005")
    check("out 10/11 02:38 = loading day 09/11 PM (Date Out + Time Out - 6 h)", (w5.day, w5.ap, w5.day_in), ("2026-11-09", "n", "2026-11-10"))
    check("out 20:30 = PM (after 18:00), tons, plate normalised", (t.net_t, t.ap, t.plate, t.market), (60.12, "n", "73H03159", "Oversea"))
    check("a 1900 Date Out falls back to Date In", db.session.get(CoalRptWeigh, "W05000004").day, "2026-11-10")
    a1 = db.session.get(CoalRptReady, "a-1")
    check("readiness 'Transportion Company' read as the company", (a1.reg_date, a1.company, a1.sub, a1.plate), ("2026-11-10", "PTS", "PTS-VTPL", "73H03159"))

d = boss.get("/api/coalrpt/data").get_json()
c = {x["contract"]: x for x in d["contracts"]}
check("contract: Ton/trp, extension, market", (c["151Coal/KCL-XPPL/2026"]["tonPerTrip"], c["151Coal/KCL-XPPL/2026"]["extension"], c["151Coal/KCL-XPPL/2026"]["export"]), (32.0, "2027-02-28", "Domestic"))
check("to-date totals per contract (whole history)", d["totals"]["COAL OFFTAKE AGREEMENT 291-PO8"]["n"], 3)
check("compact rows: 5 tickets, 3 registrations", (len(d["w"]), len(d["r"])), (5, 3))
check("last upload recorded per list", (d["meta"]["weigh"]["by"], d["meta"]["contracts"]["file"]), ("boss", "1 Calculation file - 20261110.xlsx"))

print("\nA daily export replaces only the days it covers")
r = boss.post("/api/coalrpt/upload?kind=ready", data={"file": (export_ready("10/11/2026", [("b-1", "74H-019.66"), ("b-2", "99H-032.09")]), "All contracts_Registration Trucklist_Export_2026-11-10_2026-11-11.xlsx")},
              content_type="multipart/form-data")
check("Registration Trucklist export accepted", r.get_json().get("done", {}).get("ready", {}).get("rows"), 2)
with app.app_context():
    days = sorted((x.id, x.reg_date) for x in CoalRptReady.query.all())
check("10/11 replaced by the export, 09/11 kept", days, [("a-3", "2026-11-09"), ("b-1", "2026-11-10"), ("b-2", "2026-11-10")])
r = boss.post("/api/coalrpt/upload?kind=weigh", data={"file": (export_ready("10/11/2026", [("x", "y")]), "wrong.xlsx")},
              content_type="multipart/form-data")
check("a file without the list's table is refused, nothing written", (r.status_code, "Input_Actual" in r.get_json()["error"]), (400, True))

print("\nThe lists on the Data tab")
L = boss.get("/api/coalrpt/list?kind=weigh").get_json()
check("loading list newest first", [x["id"] for x in L["rows"]][:1] in (["W05000002"], ["W05000003"], ["W05000004"]), True)
L = boss.get("/api/coalrpt/list?kind=weigh&q=73H-031").get_json()
check("search by truck as typed (73H-031)", sorted(x["id"] for x in L["rows"]), ["W05000001", "W05000002"])
L = boss.get("/api/coalrpt/list?kind=ready&q=KCL").get_json()
check("readiness search by contract / company", [x["id"] for x in L["rows"]], ["a-3"])
check("contract list", boss.get("/api/coalrpt/list?kind=contracts").get_json()["total"], 2)
check("view-only users see the lists", client("look").get("/api/coalrpt/list?kind=ready").status_code, 200)
check("...but cannot upload", client("look").post("/api/coalrpt/upload?kind=all", data={"file": (calc_file(), "x.xlsx")},
                                                  content_type="multipart/form-data").status_code, 403)
r = boss.post("/api/coalrpt/readiness/remove", json={"from": "2026-11-10", "to": "2026-11-10"}).get_json()
check("remove register dates", (r["removed"], r["total"]), (2, 1))


print("\nThe daily e-mail report (Daily tab)")
from app import coal_report as CR                                  # noqa: E402
from app.models import KVStore                                     # noqa: E402
with app.app_context():
    import json as _j
    CR._DAILY_CACHE.clear()
    db.session.query(CoalRptWeigh).delete(); db.session.query(CoalRptReady).delete()
    rows = [
        # (ticket, plate, day, ap, day_in, tons, contract)
        ("T1", "73H-031.59", "2026-11-10", "d", "2026-11-10", 46.0, "Coal Offtake Agreement 291-PO8"),
        ("T2", "73H-031.59", "2026-11-10", "n", "2026-11-11", 61.0, "Coal Offtake Agreement 291-PO8"),
        ("T3", "ບກ 2369", "2026-11-10", "d", "2026-11-10", 33.0, "151Coal/KCL-XPPL/2026"),     # space removed by the ticket key
        ("T4", "ບກ9999", "2026-11-10", "d", "2026-11-10", 36.0, "151Coal/KCL-XPPL/2026"),      # not registered
        ("T5", "74H-019.66", "2026-11-09", "d", "2026-11-09", 45.0, "Coal Offtake Agreement 291-PO8")]
    for t, p, d, ap, di, tons, c in rows:
        db.session.add(CoalRptWeigh(id=t, plate=CR.norm_plate(p), plate_raw=p, day=d, ap=ap, day_in=di, net_t=tons, contract=c, market=""))
    for i, (d, p, country, c, comp) in enumerate([
            ("2026-11-10", "73H-031.59", "Vietnam", "Coal Offtake Agreement 291-PO8", "PTS"),
            ("2026-11-10", "74H-019.66", "Vietnam", "Coal Offtake Agreement 291-PO8", "Bao Binh"),
            ("2026-11-10", "LAບກ2369", "Laos", "151Coal/KCL-XPPL/2026", "KCL"),               # Lao plate over 7: characters 3-8
            ("2026-11-09", "74H-019.66", "Vietnam", "Coal Offtake Agreement 291-PO8", "Bao Binh")]):
        db.session.add(CoalRptReady(id="r%d" % i, reg_date=d, plate=CR.norm_plate(p), plate_raw=p, country=country, contract=c, company=comp, sub=comp))
    db.session.commit()
    contracts = [
        {"customer": "Namtien", "export": "Oversea", "term": "EXW", "endUser": "N/A", "contract": "Coal Offtake Agreement 291-PO8",
         "start": "2026-09-25", "end": "2026-12-25", "extension": "", "gar": "FC 5000 Kcal", "transporter": "NT", "qty": 1000, "tonPerTrip": 60, "status": "Ongoing"},
        {"customer": "Khammouane", "export": "Domestic", "term": "EXW", "endUser": "N/A", "contract": "151Coal/KCL-XPPL/2026",
         "start": "2026-09-19", "end": "2026-10-31", "extension": "", "gar": "FC 4600 Kcal", "transporter": "KCL", "qty": 2000, "tonPerTrip": 32, "status": "Ongoing"},
        {"customer": "MHC", "export": "Domestic", "contract": "141Coal/MHC-XPPL/2026", "start": "2026-06-09", "end": "2026-08-31", "qty": 5, "tonPerTrip": 32, "status": "Complete"}]
    kv = db.session.get(KVStore, "coalRptContracts_v1") or KVStore(key="coalRptContracts_v1"); kv.value = _j.dumps(contracts); db.session.add(kv); db.session.commit()
R = boss.get("/api/coalrpt/daily?day=2026-11-10").get_json()
st = {r["contract"]: r for r in R["status"]}
check("only Ongoing contracts, e-mail order (Namtien before Khammouane)", [r["customer"] for r in R["status"]], ["Namtien", "Khammouane"])
check("Contract status: day tons and to date (up to the day)", (st["Coal Offtake Agreement 291-PO8"]["day"], st["Coal Offtake Agreement 291-PO8"]["toDate"]), (107.0, 152.0))
pl = {r["contract"]: r for r in R["plan"]}
p8, kc = pl["Coal Offtake Agreement 291-PO8"], pl["151Coal/KCL-XPPL/2026"]
check("Quantity = contract qty - to date", p8["quantity"], 848.0)
check("Plan truck = Quantity / Ton per trip, rounded up (848/60)", p8["plan"], 15)
check("Plan truck / day = Plan truck / days left (15 over 45 days to 25/12)", (p8["perDay"], p8["daysLeft"]), (1, 45))
check("Variance = trucks on the day - plan per day", p8["variance"], 2 - 1)
check("ended contract still Ongoing: planned to the end of the month, with a remark", (kc["refEnd"], kc["daysLeft"], "ended 31/10/26" in kc["remark"]), ("2026-11-30", 20, True))
check("...the contract list keeps its own end date", st["151Coal/KCL-XPPL/2026"]["end"], "2026-10-31")
check("Truck register = registrations of the day", (p8["register"], kc["register"]), (2, 1))
check("volume bands: 46 t -> 40-50t, 61 t -> 61-65t", p8["bands"], [0, 0, 0, 1, 0, 1, 0])
check("Day / Night of the last 7 days", [d for d in R["dayNight"] if d["date"] >= "2026-11-09"], [{"date": "2026-11-09", "day": 1, "night": 0}, {"date": "2026-11-10", "day": 3, "night": 1}])
bs = {(d["customer"], d["company"]): (d["reg"], d["act"], d["nreg"]) for d in R["bySub"]}
check("Truck register match: contract + truck + date, Lao plate chars 3-8, ticket spaces removed",
      (bs[("Namtien", "PTS")], bs[("Khammouane", "KCL")], bs[("Khammouane", "No data")]), ((1, 2, 0), (1, 1, 0), (0, 0, 1)))
check("Daily chart point for the day", [(d["reg"], d["act"], d["nreg"]) for d in R["daily"] if d["date"] == "2026-11-10"], [(3, 3, 1)])
check("Weekly chart = Oversea only (ISO week 46: the Khammouane rows are Domestic)", [(w["reg"], w["act"], w["nreg"]) for w in R["weekly"] if w["label"] == "46"], [(3, 3, 0)])
print("\n" + ("%d FAILED" % FAIL if FAIL else "ALL PASS"))
sys.exit(1 if FAIL else 0)
