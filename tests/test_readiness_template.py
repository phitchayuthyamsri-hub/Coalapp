# -*- coding: utf-8 -*-
"""The subcontractor page hands out the readiness template itself (06/11/2026).

Run: python tests/test_readiness_template.py   (PYTHONIOENCODING=utf-8 on Windows)

One file per company with its own active trucks and drivers on it, and the
drop-downs the upload accepts. What matters is the round trip: the file as
downloaded, with Status filled in, must read back through the same parser the
upload uses, with nothing refused.
"""
import os
import sys
import io
import tempfile
from datetime import datetime, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

_tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL="sqlite:///" + os.path.join(_tmp, "t.db").replace("\\", "/"),
    SECRET_KEY="test-only-not-a-real-key", COALAPP_ENV="")

from openpyxl import load_workbook                                # noqa: E402
from app import create_app                                        # noqa: E402
from app import readiness_import as ri                            # noqa: E402
from app.models import db, User, Truck, Subcontractor, Route      # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


app = create_app()
with app.app_context():
    bbc = Subcontractor.query.filter_by(name="Bao Binh").first() or Subcontractor(name="Bao Binh", short="BBC")
    pts = Subcontractor.query.filter_by(name="PTS").first() or Subcontractor(name="PTS", short="PTS")
    db.session.add_all([bbc, pts])
    db.session.flush()
    if not Route.query.filter_by(name="Mine : A Ngo").first():
        db.session.add(Route(name="Mine : A Ngo", kind="fronthaul", launched=True, sequence=[]))
    db.session.add_all([
        Truck(plate="43H22582", status="online", driver="NGUYEN HONG VUONG", subcontractor_id=bbc.id),
        Truck(plate="29E33234", status="online", driver="HA VAN THANG", subcontractor_id=bbc.id),
        Truck(plate="43H12895", status="deactivated", driver="NGUYEN DUY HAI", subcontractor_id=bbc.id),
        Truck(plate="74H01966", status="online", driver="Le Quang Tuan", subcontractor_id=pts.id)])
    users = {}
    for name, role, sid in (("boss", "admin", None), ("bbcuser", "subcontractor", bbc.id)):
        u = User(username=name, role=role)
        u.set_password("x" * 12)
        u.subcontractor_id = sid
        db.session.add(u)
        db.session.flush()
        users[name] = str(u.id)
    db.session.commit()
    BBC, PTS = bbc.id, pts.id


def client(who):
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = users[who]
        s["_fresh"] = True
    return c


admin, sub = client("boss"), client("bbcuser")

print("the download")
r = admin.get("/api/shift/template?subcontractor_id=%d&date=2026-11-07" % BBC)
check("an xlsx comes back", (r.status_code, r.mimetype.endswith("sheet")), (200, True))
check("...named for the company and the day",
      "BBC - Daily readiness template 0711.xlsx" in r.headers.get("Content-Disposition", ""), True)
wb = load_workbook(io.BytesIO(r.data))
ws = wb["Readiness"]
check("the sheet is called Readiness", wb.sheetnames[0], "Readiness")
check("the header is on row 6", [c.value for c in ws[6]][:5], ["No", "Plate", "Driver", "Route", "Status"])
plates = [ws.cell(row=r_, column=2).value for r_ in range(7, 12) if ws.cell(row=r_, column=2).value]
check("its own active trucks, not the deactivated one, not PTS's", plates, ["29E33234", "43H22582"])
check("...with their drivers", ws.cell(row=7, column=3).value, "HA VAN THANG")
check("Status offers exactly what the upload accepts",
      [c.value for c in wb["Lists"]["B"][1:]], list(ri.STATUS_CHOICES))
check("no company picked: refused, not an empty file",
      admin.get("/api/shift/template").status_code, 400)

print("\nfilled in and read back by the upload's own parser")
ws.cell(row=7, column=4, value="Mine : A Ngo")
ws.cell(row=7, column=5, value="BH")
ws.cell(row=7, column=6, value="Empty")
ws.cell(row=7, column=7, value="Lalay border")
ws.cell(row=7, column=8, value=datetime(2026, 11, 7))
ws.cell(row=7, column=9, value=time(7, 30))
ws.cell(row=8, column=5, value="Repair")
path = os.path.join(_tmp, "filled.xlsx")
wb.save(path)
got = ri.parse(path)
rows = {x["plate"]: x for x in got["rows"]}
check("both trucks are read", sorted(rows), ["29E33234", "43H22582"])
check("...the BH one with its route and arrival",
      (rows["29E33234"].get("activity"), rows["29E33234"].get("route"),
       rows["29E33234"].get("arrive_date"), rows["29E33234"].get("arrive_time")),
      ("BH", "Mine : A Ngo", "2026-11-07", "07:30"))
check("...the other with its reason", rows["43H22582"].get("activity"), "Repair")
check("...and the load in its own column", rows["29E33234"].get("status"), "Empty")
check("nothing in it is refused", ri.problems(got["rows"]), [])

print("\na subcontractor login")
r = sub.get("/api/shift/template?subcontractor_id=%d" % PTS)
wb2 = load_workbook(io.BytesIO(r.data))
check("asking for another company still gets its own trucks",
      [c.value for c in wb2["Readiness"]["B"][6:8]], ["29E33234", "43H22582"])

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
