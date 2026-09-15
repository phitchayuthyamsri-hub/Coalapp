# -*- coding: utf-8 -*-
"""The readiness importer reads BOTH sheet layouts in use.

Run: python tests/test_readiness_import.py

The Bac Nam template splits the declaration over three columns - Leg (FH/BH),
Status (Loaded/Empty) and Activity (the reason) - while the newer layout has one
Status column (FH/BH/reason) and a separate Loaded / Empty column. The importer
once mapped all three Bac Nam columns onto one field, the last (usually blank)
won, and a whole uploaded sheet arrived with no leg and no load state.
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
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(58)
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


def by_plate(path):
    res = ri.parse(path)
    os.remove(path)
    return {r["plate"]: r for r in res["rows"]}, res["warnings"]


# ── the Bac Nam template: Leg / Status (load) / Activity (reason) ────────────
BAC_NAM = ["No", "Plate", "Driver", "Leg", "Location", "Status", "Activity",
           "Date arrive Mine", "Time arrive Mine", "Back in service", "Remark"]
rows, warns = by_plate(sheet(BAC_NAM, [
    [1, "20C10615", "Driver A", "BH", "XPPL Mine", "Empty", None,
     datetime(2026, 9, 16), "05:00", None, "at the mine, ready to load"],
    [2, "20C10770", "Driver B", "FH", "XPPL Mine", "Loaded", None,
     None, None, None, "loaded, leaving the mine"],
    [3, "20C21702", "Driver C", None, "Workshop", "Empty", "Maintenance",
     None, None, "2026-09-18", None],
    [4, "20H01353", "Driver D", "BH", "QL49", "Empty",
     "Unloading -> Maintenace -> 06/06 back to Mine", None, None, None, None],
    [5, "20H01370", "Driver E", "FH", "Lalay border", "Loaded",
     "waiting for the gate", None, None, None, None],
]))
print("Bac Nam template")
check("BH truck: leg read from Leg", rows["20C10615"]["activity"], "BH")
check("BH truck: load read from Status", rows["20C10615"]["status"], "Empty")
check("BH truck: arrival date kept", rows["20C10615"]["arrive_date"], "2026-09-16")
check("BH truck: remark kept verbatim", rows["20C10615"]["remark"],
      "at the mine, ready to load")
check("BH truck is running", ri.is_running(rows["20C10615"]["activity"]), True)
check("FH truck: leg and load", (rows["20C10770"]["activity"], rows["20C10770"]["status"]),
      ("FH", "Loaded"))
check("a reason in Activity is the status", rows["20C21702"]["activity"], "Maintenance")
check("...and the truck is not running", ri.is_running(rows["20C21702"]["activity"]), False)
check("a not-running reason beats the leg",
      ri.is_running(rows["20H01353"]["activity"]), False)
check("a running note is not lost - it joins the remark",
      (rows["20H01370"]["activity"], rows["20H01370"]["remark"]),
      ("FH", "waiting for the gate"))
check("no missing-column warning for this layout",
      [w for w in warns if "Loaded" in w or "Status" in w], [])

# ── the newer layout: one Status column and a Loaded / Empty column ─────────
rows, warns = by_plate(sheet(
    ["Plate", "Status", "Loaded / Empty", "Location", "Date arrive Mine",
     "Time arrive Mine", "Remark"],
    [["20C10615", "BH", "Empty", "QL49", "16-09-26", "07:00", "x"],
     ["20C10770", "Breakdown", "Empty", "Garage", None, None, "gearbox"]]))
print("\nnewer layout")
check("Status carries the leg", rows["20C10615"]["activity"], "BH")
check("Loaded / Empty carries the load", rows["20C10615"]["status"], "Empty")
check("day-first date", rows["20C10615"]["arrive_date"], "2026-09-16")
check("Status carries the reason", rows["20C10770"]["activity"], "Breakdown")
check("...not running", ri.is_running(rows["20C10770"]["activity"]), False)

# ── Vietnamese load words in a Status column ─────────────────────────────────
rows, warns = by_plate(sheet(["Plate", "Leg", "Status"],
                             [["20C10615", "FH", "Có hàng"], ["20C10770", "BH", "Rỗng"]]))
print("\nVietnamese load words")
check("Có hàng is Loaded", rows["20C10615"]["status"], "Loaded")
check("Rỗng is Empty", rows["20C10770"]["status"], "Empty")
check("the leg still comes from Leg", rows["20C10770"]["activity"], "BH")

# ── nothing about load at all ────────────────────────────────────────────────
rows, warns = by_plate(sheet(["Plate", "Status"], [["20C10615", "FH"]]))
print("\nno load column")
check("the leg is read", rows["20C10615"]["activity"], "FH")
check("the missing Loaded / Empty is warned about",
      any("Loaded / Empty" in w for w in warns), True)

print("\n  %d FAILING" % FAIL if FAIL else "\n  all pass")
sys.exit(1 if FAIL else 0)
