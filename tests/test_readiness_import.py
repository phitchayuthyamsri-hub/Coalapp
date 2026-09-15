# -*- coding: utf-8 -*-
"""The readiness importer reads ONE layout, and refuses the old ones.

Run: python tests/test_readiness_import.py

  No · Plate · Driver · Status · Location · Loaded / Empty ·
  Date arrive Mine · Time arrive Mine · Back in service · Remark

Status is FH, BH or the reason a truck is not running; Loaded / Empty is its own
column. The old template split this over Leg / Status / Activity, and reading
both meant guessing - a guess that once emptied a whole sheet of its FH/BH. Old
layouts are now refused with a message, never half-read.
"""
import importlib.util
import os
import sys
import tempfile
from datetime import datetime

from openpyxl import Workbook

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "readiness_import", os.path.join(HERE, "..", "app", "readiness_import.py"))
ri = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ri)

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(60)
          + ("" if ok else "got %r want %r" % (got, want)))


def sheet(headers, rows, lead=5):
    """A workbook shaped like the real ones: a title block, then the header row."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Readiness"
    for i in range(lead):
        ws.append(["DAILY READINESS" if i == 0 else None])
    ws.append(headers)
    for r in rows:
        ws.append(r)
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    wb.save(path)
    return path


def parsed(path):
    res = ri.parse(path)
    os.remove(path)
    return res, {r["plate"]: r for r in res["rows"]}


NEW = ["No", "Plate", "Driver", "Status", "Location", "Loaded / Empty",
       "Date arrive Mine", "Time arrive Mine", "Back in service", "Remark"]

# ── the new template ────────────────────────────────────────────────────────
res, rows = parsed(sheet(NEW, [
    [1, "20C10615", "Driver A", "BH", "XPPL Mine", "Empty", datetime(2026, 9, 16), "05:00",
     None, "at the mine, ready to load"],
    [2, "20C10770", "Driver B", "fh", "XPPL Mine", "Loaded", None, None, None, None],
    [3, "20C21702", "Driver C", "Maintenance", "Workshop", "Empty", None, None,
     "18/09/2026", "engine service"],
    [4, "20H01353", "Driver D", "Unloading -> Maintenace -> back Friday", "QL49", "Empty",
     None, None, None, None],
]))
print("new template")
check("no warnings, nothing refused", (res["warnings"], res.get("error")), ([], None))
check("BH read from Status", rows["20C10615"]["activity"], "BH")
check("load read from Loaded / Empty", rows["20C10615"]["status"], "Empty")
check("arrival date and time", (rows["20C10615"]["arrive_date"], rows["20C10615"]["arrive_time"]),
      ("2026-09-16", "05:00"))
check("remark kept verbatim", rows["20C10615"]["remark"], "at the mine, ready to load")
check("fh is written FH", rows["20C10770"]["activity"], "FH")
check("a reason in Status is the status", rows["20C21702"]["activity"], "Maintenance")
check("...not running", ri.is_running(rows["20C21702"]["activity"]), False)
check("back in service, day first", rows["20C21702"]["back_in_service"], "2026-09-18")
check("a sentence with a not-running word is not running",
      ri.is_running(rows["20H01353"]["activity"]), False)

# ── Vietnamese load words ────────────────────────────────────────────────────
res, rows = parsed(sheet(["Plate", "Status", "Loaded / Empty"],
                         [["20C10615", "FH", "Có hàng"], ["20C10770", "BH", "Rỗng"]]))
print("\nVietnamese load words")
check("Có hàng is Loaded", rows["20C10615"]["status"], "Loaded")
check("Rỗng is Empty", rows["20C10770"]["status"], "Empty")

# ── the old template is refused, not half-read ──────────────────────────────
OLD = ["No", "Plate", "Driver", "Leg", "Location", "Status", "Activity",
       "Date arrive Mine", "Time arrive Mine", "Back in service", "Remark"]
res, rows = parsed(sheet(OLD, [[1, "20C10615", "A", "BH", "XPPL Mine", "Empty", None,
                                 None, None, None, None]]))
print("\nold layouts")
check("the Leg / Status / Activity template imports nothing", len(rows), 0)
check("...and says it is the old template", "old template" in (res.get("error") or ""), True)
check("...naming the columns that give it away",
      "Leg" in res["error"] and "Activity" in res["error"], True)

res, rows = parsed(sheet(["Plate", "Status", "Reason"], [["20C10615", "FH", "Maintenance"]]))
check("a separate Reason column is refused too", (len(rows), bool(res.get("error"))), (0, True))

# ── mistakes in the new template are reported, never guessed ────────────────
res, rows = parsed(sheet(["Plate", "Status", "Loaded / Empty"],
                         [["20C10615", "Empty", ""], ["20C10770", "BH", "Empty"]]))
print("\nmistakes")
check("Loaded/Empty typed into Status is not a status", rows["20C10615"]["activity"], "")
check("...and it is warned about", any("Status column" in w for w in res["warnings"]), True)
check("the correct row beside it is untouched", rows["20C10770"]["activity"], "BH")

res, rows = parsed(sheet(["Plate", "Status"], [["20C10615", "FH"]]))
check("a missing Loaded / Empty column is warned about",
      any("Loaded / Empty" in w for w in res["warnings"]), True)

res, rows = parsed(sheet(["Plate", "Status", "Note"], [["20C10615", "FH", "waiting at gate"]]))
check("a Note column is a remark", rows["20C10615"]["remark"], "waiting at gate")

print("\n  %d FAILING" % FAIL if FAIL else "\n  all pass")
sys.exit(1 if FAIL else 0)
