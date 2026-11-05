# -*- coding: utf-8 -*-
"""Data issues: what a subcontractor sent wrong, kept on record (05/11/2026).

Run: python tests/test_data_issues.py   (PYTHONIOENCODING=utf-8 on Windows)

Lists are entered as the companies send them and not repaired, so that the gap
costs whoever left it. The record has to say when it was first reported and
in which file, stay until it is fixed, and be the control tower's own: an admin
writes it, the companies it is about do not read it.
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

from app import create_app                              # noqa: E402
from app.models import db, User, Subcontractor          # noqa: E402

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
    db.session.add(bbc)
    db.session.flush()
    ids = {}
    for name, role in (("boss", "admin"), ("plan", "planner"), ("huy", "subcontractor")):
        u = User(username=name, role=role)
        u.set_password("x" * 12)
        if role == "subcontractor":
            u.subcontractor_id = bbc.id
        db.session.add(u)
        db.session.flush()
        ids[name] = str(u.id)
    db.session.commit()
    BBC = bbc.id


def client(who):
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = ids[who]
        s["_fresh"] = True
    return c


admin, planner, sub = client("boss"), client("plan"), client("huy")

print("an admin logs an issue")
r = admin.post("/api/data-issues", json={
    "subcontractor_id": BBC, "plate": "29E33234", "kind": "phone", "sent": "+847 288 075",
    "detail": "9 digits - cannot be dialled", "source": "BBC TRUCK TMS - V2.xlsx",
    "first_seen": "2026-11-03", "last_seen": "2026-11-05"})
j = r.get_json()
check("it is saved", r.status_code, 200)
iid = j["issue"]["id"]
check("...open", j["issue"]["status"], "open")
check("...with what they sent, exactly", j["issue"]["sent"], "+847 288 075")
check("...and since when", (j["issue"]["first_seen"], j["issue"]["last_seen"]), ("2026-11-03", "2026-11-05"))
r = admin.post("/api/data-issues", json={"plate": "43H22582"})
check("an issue saying nothing is refused", r.status_code, 400)

print("\nwho sees it")
lst = planner.get("/api/data-issues").get_json()
check("the planner reads the list", [i["plate"] for i in lst["issues"]], ["29E33234"])
check("...named by company", lst["issues"][0]["company"], "BBC")
check("...but may not write to it", planner.post("/api/data-issues", json={"detail": "x"}).status_code, 403)
check("the company it is about cannot read it", sub.get("/api/data-issues").status_code, 403)
check("...nor open the page", sub.get("/data-issues").status_code, 403)
check("the page opens for the admin", admin.get("/data-issues?embed=1").status_code, 200)

print("\nseen again, then fixed")
r = admin.post("/api/data-issues/%d" % iid, json={"last_seen": "2026-11-07"})
check("a later list moves 'still in' on", r.get_json()["issue"]["last_seen"], "2026-11-07")
check("...and keeps when it was first reported", r.get_json()["issue"]["first_seen"], "2026-11-03")
r = admin.post("/api/data-issues/%d" % iid, json={"status": "fixed", "fixed_note": "V6 has 0357 288 075"})
i = r.get_json()["issue"]
check("fixed", i["status"], "fixed")
check("...by whom, with the note", (i["fixed_by"], i["fixed_note"]), ("boss", "V6 has 0357 288 075"))
check("it stays on record", len(planner.get("/api/data-issues").get_json()["issues"]), 1)
r = admin.post("/api/data-issues/%d" % iid, json={"status": "open"})
check("reopened, the fix is cleared", (r.get_json()["issue"]["status"], r.get_json()["issue"]["fixed_by"]), ("open", ""))

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
