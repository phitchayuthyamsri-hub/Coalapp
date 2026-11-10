# -*- coding: utf-8 -*-
"""Opportunity lost for the Scorecard: trucks declared BH with no time (10/11/2026).

Run: python tests/test_bh_untimed.py   (PYTHONIOENCODING=utf-8 on Windows)

/api/shift/bh-untimed lists every truck a company declared coming back (BH)
without a time at the mine, with the remark it typed sorted into: still on its
previous trip ('Bốc mỏ 30/09'), breakdown / repair ('Xe hỏng', 'sửa xe'), or
nothing said. A company login sees its own sheets only.
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

from app import create_app                                        # noqa: E402
from app.models import db, User, Subcontractor, DailyList, DailyListRow  # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64) + ("" if ok else "got %r want %r" % (got, want)))


app = create_app()
with app.app_context():
    def _sub(name):
        s = Subcontractor.query.filter_by(name=name).first() or Subcontractor(name=name, short=name)
        db.session.add(s)
        return s
    bn, hs = _sub("Bac Nam"), _sub("Hoanh Son")
    db.session.flush()
    adm = User(username="boss", role="admin"); adm.set_password("x" * 12)
    sub = User(username="huytrv", role="subcontractor", subcontractor_id=bn.id); sub.set_password("x" * 12)
    db.session.add_all([adm, sub])
    l1 = DailyList(list_date="2026-10-01", subcontractor_id=bn.id, state="confirmed")
    l2 = DailyList(list_date="2026-10-01", subcontractor_id=hs.id, state="confirmed")
    l3 = DailyList(list_date="2026-10-09", subcontractor_id=bn.id, state="confirmed")
    db.session.add_all([l1, l2, l3])
    db.session.flush()
    for lid, plate, note, hhmm, remark in (
            (l1.id, "20H-013.81", "BH", "", "19h 30/09 bốc mỏ"),
            (l1.id, "20H00709", "BH", "", "Xe hỏng trên đường vào mỏ"),
            (l1.id, "20H01474", "BH", "", "Về A Ngo sửa xe"),
            (l1.id, "20H00745", "BH", "", ""),
            (l1.id, "20H01491", "BH", "07:00", ""),          # has a time: not lost
            (l1.id, "20H01398", "FH", "", ""),               # running out: not BH
            (l2.id, "38H03034", "BH", "", ""),
            (l3.id, "20H01410", "BH", "", "")):              # outside the period
        db.session.add(DailyListRow(list_id=lid, plate=plate, key=plate, note=note,
                                    arrive_hhmm=hhmm, remark=remark, ready=True))
    db.session.commit()
    ids = {"boss": str(adm.id), "huytrv": str(sub.id)}


def client(name):
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = ids[name]
        s["_fresh"] = True
    return c


j = client("boss").get("/api/shift/bh-untimed?from=2026-10-01&to=2026-10-05").get_json()
rows = {r["plate"]: r for r in j["rows"]}
check("BH with no time only, both companies, inside the period",
      sorted(rows), ["20H-013.81", "20H00709", "20H00745", "20H01474", "38H03034"])
check("'bốc mỏ' = still on its previous trip", rows["20H-013.81"]["group"], "prev")
check("'Xe hỏng' = breakdown", rows["20H00709"]["group"], "repair")
check("'sửa xe' = repair", rows["20H01474"]["group"], "repair")
check("nothing said = left for the GPS to answer", rows["20H00745"]["group"], "")
check("the plate is keyed as the page keys it", rows["20H-013.81"]["key"], "20H01381")
check("day counts: declared / BH / untimed (Bac Nam + Hoanh Son)",
      j["days"]["2026-10-01"], {"declared": 7, "bh": 6, "untimed": 5})
own = client("huytrv").get("/api/shift/bh-untimed?from=2026-10-01&to=2026-10-31").get_json()
check("a company login sees its own sheets only",
      sorted({r["company"] for r in own["rows"]}), ["Bac Nam"])
check("...all of its own period", len(own["rows"]), 5)
check("a bad period is refused", client("boss").get("/api/shift/bh-untimed?from=x&to=y").status_code, 400)

with app.app_context():
    from app.models import PlanSnapshot
    from app import tool_link
    db.session.add(PlanSnapshot(week_start="2026-10-26", day="2026-10-27", issued_by="boss", rows=[
        {"plate": "20H01381", "day": "2026-10-27", "route_name": "Mine : A Ngo : Chan May",
         "t": {"arrive_mine": "2026-10-27T07:00", "back": "2026-10-29T07:00"}}]))
    db.session.commit()
    check("the plan feed carries the route (Scorecard route slicer)",
          tool_link._plan(None)["20H01381|2026-10-27"]["route"], "Mine : A Ngo : Chan May")

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
