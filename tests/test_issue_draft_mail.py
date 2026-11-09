# -*- coding: utf-8 -*-
"""Issuing a revised day emails the planner a draft (09/11/2026).

Run: python tests/test_issue_draft_mail.py   (PYTHONIOENCODING=utf-8 on Windows)

The team's daily email - "Coal loading Plan Mine-ChanMay / Mine-A Ngo /
A Ngo-ChanMay as of 10 Nov 2026" with the Revision file renamed
"Plan Load_2026-11-10.xlsx" - comes to the planner on Issue, to review the
Excel file before forwarding it himself. Nobody else is mailed. Issuing the
same day again is abnormal: the server refuses until the page confirms.
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
    SECRET_KEY="test-only-not-a-real-key", COALAPP_ENV="",
    MAIL_RELAY_URL="https://relay.invalid/test", MAIL_RELAY_SECRET="test-only")
os.environ.pop("COAL_PLAN_DRAFT_TO", None)

from openpyxl import load_workbook                                # noqa: E402
from app import create_app                                        # noqa: E402
from app import shift_routes as sr                                # noqa: E402
from app import mailer                                            # noqa: E402
from app.models import (db, User, Truck, Subcontractor, DailyList,  # noqa: E402
                        DailyListRow, PlanSnapshot)

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


SENT = []


def fake_send(to, subject, html="", text="", cc="", files=None, timeout=45):
    SENT.append({"to": to, "cc": cc, "subject": subject, "html": html, "text": text,
                 "files": files or []})
    return True, "ok"


mailer.send_mail = fake_send

T = datetime.utcnow() + sr.LOCAL_OFFSET
RUN = (T + timedelta(days=1)).strftime("%Y-%m-%d")
RD = datetime.strptime(RUN, "%Y-%m-%d")

app = create_app()
with app.app_context():
    sub = Subcontractor.query.filter_by(name="Bac Nam").first() or Subcontractor(name="Bac Nam")
    db.session.add(sub)
    db.session.flush()
    adm = User(username="plan@nt", role="admin")
    adm.set_password("x" * 12)
    db.session.add(adm)
    for p in ("20H01469", "20H01474"):
        db.session.add(Truck(plate=p, status="online", subcontractor_id=sub.id))
    dl = DailyList(list_date=RUN, subcontractor_id=sub.id, state="draft")
    db.session.add(dl)
    db.session.flush()
    for plate, hhmm in (("20H01469", "06:00"), ("20H01474", "07:30")):
        db.session.add(DailyListRow(list_id=dl.id, plate=plate, key=plate, note="BH",
                                    ready=True, state="applied", arrive_date=RUN,
                                    arrive_hhmm=hhmm))
    db.session.commit()
    uid = str(adm.id)

c = app.test_client()
with c.session_transaction() as s:
    s["_user_id"] = uid
    s["_fresh"] = True

print("the first issue")
r = c.post("/api/shift/revision/issue", json={"date": RUN})
j = r.get_json() or {}
check("issued", r.status_code, 200)
check("one email", len(SENT), 1)
m = SENT[0] if SENT else {"files": [("", b"", "")]}
check("to the planner only, nobody in cc", (m.get("to"), m.get("cc")),
      ("phitchayuth.ya@logisticsasia.co.th", ""))
check("the team's subject",
      m.get("subject"),
      "Coal loading Plan Mine-ChanMay / Mine-A Ngo / A Ngo-ChanMay as of %s" % RD.strftime("%d %b %Y"))
check("the team's sentence", "Please see coal plan loading as of %s, thank you." % RD.strftime("%d %B %Y") in m.get("text", ""), True)
check("signed by Phitchayuth", "Phitchayuth Yamsri" in m.get("html", "") and "Logistics Asia ( LA )" in m.get("text", ""), True)
name, data, mime = m["files"][0]
check("the file is named as the team names it", name, "Plan Load_%s.xlsx" % RUN)
wb = load_workbook(io.BytesIO(data))
check("it is the Revision workbook", wb.sheetnames, ["Revision", "Figures used"])
check("...of the issued plan, not a working one", str(wb["Revision"]["A2"].value).startswith("Issued "), True)
check("...with the two trucks", sorted(x.value for x in wb["Revision"]["B"][3:5]), ["20H01469", "20H01474"])
check("the page is told it went", (j.get("mail") or {}).get("sent"), True)

print("\nthe same day again")
r = c.post("/api/shift/revision/issue", json={"date": RUN})
j = r.get_json() or {}
check("refused until confirmed", (r.status_code, j.get("reissue_needed")), (409, True))
check("says who issued it", j.get("last_by"), "plan@nt")
with app.app_context():
    check("nothing written", PlanSnapshot.query.filter_by(day=RUN).count(), 1)
check("no email", len(SENT), 1)
r = c.post("/api/shift/revision/issue", json={"date": RUN, "reissue": True})
check("confirmed: issued again", r.status_code, 200)
check("...and the draft mailed again", len(SENT), 2)
r = c.post("/api/shift/revision/issue", json={"date": RUN})
check("third time: warned again, counting 2", (r.status_code, (r.get_json() or {}).get("times")), (409, 2))

print("\nno relay configured")
os.environ.pop("MAIL_RELAY_URL")
r = c.post("/api/shift/revision/issue", json={"date": RUN, "reissue": True})
j = r.get_json() or {}
check("the issue still stands", r.status_code, 200)
check("the page is told the mail did not go", ((j.get("mail") or {}).get("sent"), (j.get("mail") or {}).get("why")),
      (False, "mail relay not configured"))
check("nothing sent", len(SENT), 2)

print("\na company's own issue")
s, f, _t, _h = sr._draft_mail_parts("2026-11-10", "Hoanh Son")
check("subject names the company", s.endswith("as of 10 Nov 2026 - Hoanh Son"), True)
check("so does the file", f, "Plan Load_2026-11-10_HoanhSon.xlsx")

print("\nthe download button")
r = c.get("/api/shift/revision.xlsx?date=" + RUN)
check("still downloads the same workbook", (r.status_code, load_workbook(io.BytesIO(r.data)).sheetnames),
      (200, ["Revision", "Figures used"]))

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
