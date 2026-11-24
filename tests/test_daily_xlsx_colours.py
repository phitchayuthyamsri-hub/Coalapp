# -*- coding: utf-8 -*-
"""The Daily page's Excel file is coloured like the page (24/11/2026).

Run: python tests/test_daily_xlsx_colours.py   (PYTHONIOENCODING=utf-8 on Windows)
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
_tmp = tempfile.mkdtemp()
os.environ.update(DATABASE_URL="sqlite:///" + os.path.join(_tmp, "t.db").replace("\\", "/"),
                  SECRET_KEY="test-only-not-a-real-key", COALAPP_ENV="")

from openpyxl import load_workbook                     # noqa: E402
from openpyxl.cell.rich_text import CellRichText       # noqa: E402

from app import create_app                             # noqa: E402
from app.models import db, User                        # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(62) + ("" if ok else "got %r want %r" % (got, want)))


app = create_app()
with app.app_context():
    u = User(username="adm", role="admin", is_admin=True)
    u.set_password("x" * 12)
    db.session.add(u)
    db.session.commit()
    uid = str(u.id)
c = app.test_client()
with c.session_transaction() as s:
    s["_user_id"], s["_fresh"] = uid, True

D = ["2026-11-23", "2026-11-24"]
payload = {
    "dates": D, "from": D[0], "to": D[1], "scope": "In fleet", "company": "BBC", "exported": "24/11/2026",
    "file": "Daily_performance_2026-11-23_to_2026-11-24_BBC.xlsx",
    "counts": [{"label": "Planned truck", "f": "planned", "total": 3, "vals": [2, 1]},
               {"label": "Came as planned", "f": "asPlanned", "total": 1, "vals": [1, 0]},
               {"label": "Did not come", "f": "noShow", "total": 2, "vals": [1, 1]}],
    "grid": [{"plate": "20H01481", "sub": "Bac Nam", "wb": True, "totals": {"circle": 1, "cross": 1},
              "cells": [{"sym": "circle", "man": False, "wb": False, "note": ""},
                        {"sym": "half", "man": True, "wb": False, "note": "+5h"}]},
             {"plate": "37H09305", "sub": "BBC", "wb": False, "totals": {},
              "cells": [{"off": "Not in the fleet yet (from 24/11) - not counted"}, {"sym": "cross"}]}],
    "detail": [{"date": D[0], "plate": "20H01481", "sub": "Bac Nam", "sym": "circle", "tip": "Plan 06:00"}],
}
r = c.post("/api/tool/daily.xlsx", json=payload)
check("the server builds the file", r.status_code, 200)
check("...as the file name the page asked for", "Daily_performance_2026-11-23_to_2026-11-24_BBC.xlsx"
      in r.headers.get("Content-Disposition", ""), True)
wb = load_workbook(io.BytesIO(r.data), rich_text=True)
check("four sheets", wb.sheetnames, ["Daily status counts", "Per-truck symbols", "Per truck per day", "About"])
ws = wb["Daily status counts"]
rgb = lambda c: (c.fill.fgColor.rgb or "")[-6:]
fnt = lambda c: (c.font.color.rgb or "")[-6:] if c.font and c.font.color else ""
check("header: the page's dark header", (rgb(ws["A4"]), fnt(ws["A4"])), ("0A1014", "FFFFFF"))
check("a status name on the darker panel", rgb(ws["A6"]), "1D272F")
check("...with its colour down the left (came as planned = green)", ws["A6"].border.left.color.rgb[-6:], "34D399")
check("the total column, darker, green number", (rgb(ws["B6"]), fnt(ws["B6"])), ("1A2630", "34D399"))
check("did not come counts are red", fnt(ws["C7"]), "F87171")
ws = wb["Per-truck symbols"]
check("symbol header ● is green, ✕ is red", (fnt(ws["C4"]), fnt(ws["F4"])), ("34D399", "F87171"))
check("totals: ● green, ✕ red on the total colour", (fnt(ws["C5"]), fnt(ws["F5"]), rgb(ws["C5"])),
      ("34D399", "F87171", "1A2630"))
cell = ws.cell(row=5, column=10).value          # 20H01481, 24/11: ◐ ◆ +5h
check("a day: ◐ purple, ◆ teal, +5h grey", [(b.text, b.font.color.rgb[-6:]) for b in cell]
      if isinstance(cell, CellRichText) else cell,
      [("◐", "A78BFA"), (" ◆", "2DD4BF"), (" +5h", "8B98A5")])
cell = ws.cell(row=6, column=10).value
check("a day: ✕ red", [(b.text, b.font.color.rgb[-6:]) for b in cell] if isinstance(cell, CellRichText) else cell,
      [("✕", "F87171")])
off = ws.cell(row=6, column=9)                   # 37H09305, 23/11: before it joined the fleet
check("a day outside the fleet dates: grey '–' with the reason on hover",
      (off.value, fnt(off), off.comment.text if off.comment else None),
      ("–", "4B5663", "Not in the fleet yet (from 24/11) - not counted"))
plate = ws["A5"].value
check("a weighbridge truck carries ⚠ WB in blue", [(b.text.strip(), b.font.color.rgb[-6:]) for b in plate]
      if isinstance(plate, CellRichText) else plate, [("20H01481", "E6EDF3"), ("⚠ WB", "2E9BFF")])
check("Truck / Subcontractor and totals stay on screen when scrolling", ws.freeze_panes, "I5")
ws = wb["Per truck per day"]
check("per day: the status in words in its colour", (ws["D5"].value, fnt(ws["D5"])), ("●  Came as planned", "34D399"))
r = c.post("/api/tool/daily.xlsx", json=dict(payload, file="../../etc/passwd"))
check("a file name cannot point anywhere", 'filename="etcpasswd.xlsx"' in r.headers.get("Content-Disposition", ""),
      True)
print()
print("ALL PASS" if not FAIL else "%d FAILED" % FAIL)
sys.exit(1 if FAIL else 0)
