# -*- coding: utf-8 -*-
"""Read a subcontractor's daily readiness sheet.

One layout, the same shape as the declaration page:

  No · Plate · Driver · Status · Location · Loaded / Empty ·
  Date arrive Mine · Time arrive Mine · Back in service · Remark

Status carries the leg while a truck is working (FH / BH) and the reason when it
is not (Maintenance, Breakdown ...). Loaded / Empty carries the load. Nothing
else is read for either.

The earlier template split this over Leg, Status (the load) and Activity (the
reason), and some sheets kept the reason in a column of its own. Reading all of
those meant guessing which column meant what, and a guess that went wrong
emptied a whole sheet of its FH/BH without a word. A sheet in any of those
layouts is now refused, with a message saying which template to use - better a
refusal than a truck in the workshop quietly counted as running.

The header row is still found by looking for a Plate column; columns may be in
any order and extra columns are ignored.
"""
import re
from datetime import datetime, time

from openpyxl import load_workbook

# header text -> field. Lowercased, punctuation stripped, before match.
HEADER_MAP = {
    "no": "no", "stt": "no",
    "plate": "plate", "licenseplate": "plate", "bienso": "plate", "truck": "plate",
    "driver": "driver", "taixe": "driver",
    "location": "location", "vitri": "location",
    # FH / BH while working, the reason when not. The one column that decides it.
    "status": "status", "trangthai": "status", "truckstatus": "status",
    "loadedempty": "load", "loadempty": "load", "loadedorempty": "load",
    "loadstatus": "load", "cohang": "load",
    "timearrivemine": "arrive_time", "timearrivalmine": "arrive_time",
    "arrivetime": "arrive_time", "giodenmo": "arrive_time",
    # older BBC sheets head these columns "Arrive Mine" / "Entry Mine Date"
    "arrivemine": "arrive_time", "arrivalmine": "arrive_time",
    "datearrivemine": "arrive_date", "datearrivalmine": "arrive_date",
    "arrivedate": "arrive_date", "ngaydenmo": "arrive_date",
    "entryminedate": "arrive_date", "entrymine": "arrive_date",
    "backinservice": "back_in_service",
    # A free note is a remark, whatever it is called.
    "remark": "remark", "remarks": "remark", "note": "remark", "ghichu": "remark",
}

# Headers from layouts that kept the leg or the reason somewhere other than
# Status. Their presence means the sheet cannot be read without guessing.
OLD_LAYOUT = {"leg", "fhbh", "activity", "reason", "lydo", "notrunningreason",
              "notrunning", "unavailablereason", "downtimereason"}

PLATE_RE = re.compile(r"^\s*\d{2}\s*[A-Za-z]", re.I)

# Whole-cell values only: "loaded, leaving the mine" is a sentence, not a load state.
_LOADED = ("loaded", "load", "full", "có hàng", "co hang")
_EMPTY = ("empty", "rỗng", "rong", "không hàng", "khong hang")
_LEGS = {"fh": "FH", "bh": "BH", "front haul": "FH", "fronthaul": "FH",
         "back haul": "BH", "backhaul": "BH"}


def _norm_header(v):
    return re.sub(r"[^a-z0-9]", "", str(v or "").lower())


def _norm_word(v):
    return re.sub(r"\s+", " ", str(v or "").strip().lower())


def norm_plate(v):
    return re.sub(r"[^A-Za-z0-9]", "", str(v or "")).upper()


def load_word(v):
    """'Loaded' / 'Empty' when the cell is a load state, else ''."""
    w = _norm_word(v)
    if w in _LOADED:
        return "Loaded"
    if w in _EMPTY:
        return "Empty"
    return ""


def leg_word(v):
    """'FH' / 'BH' when the cell is a leg, else ''."""
    return _LEGS.get(_norm_word(v), "")


def _as_hhmm(v):
    if v is None or v == "":
        return ""
    if isinstance(v, time):
        return "%02d:%02d" % (v.hour, v.minute)
    if isinstance(v, datetime):
        return "%02d:%02d" % (v.hour, v.minute)
    m = re.match(r"^\s*(\d{1,2})[:h.](\d{2})", str(v))
    return "%02d:%s" % (int(m.group(1)), m.group(2)) if m else ""


def _as_date(v):
    if v is None or v == "":
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    # Four-digit years first, so "04-09-2026" is never mistaken for a two-digit
    # form. Day always leads: "04-09-26" is 4 September, never 9 April - which is
    # the confusion the template's header warns about.
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y",
                "%d-%m-%y", "%d/%m/%y",
                "%d/%m", "%d-%m"):
        try:
            d = datetime.strptime(s, fmt)
            return d.strftime("%Y-%m-%d") if d.year > 1900 else ""
        except ValueError:
            pass
    return ""


def _find_header(ws, limit=30):
    """The header row is the first one containing a recognisable Plate column.

    -> (row, {field: [column numbers, in sheet order]}, [old-layout header texts])"""
    for r in range(1, min(ws.max_row, limit) + 1):
        cols, old = {}, []
        for c in range(1, min(ws.max_column, 20) + 1):
            raw = ws.cell(row=r, column=c).value
            n = _norm_header(raw)
            if n in OLD_LAYOUT:
                old.append(str(raw).strip())
            f = HEADER_MAP.get(n)
            if f:
                cols.setdefault(f, []).append(c)
        if "plate" in cols:
            return r, cols, old
    return None, {}, []


def parse(path):
    """-> {'rows': [...], 'header_row': n, 'columns': [...], 'warnings': [...],
           'error': message when the sheet is refused}"""
    wb = load_workbook(path, data_only=True)
    ws = None
    for name in ("Readiness", "Sheet1"):
        if name in wb.sheetnames:
            ws = wb[name]
            break
    ws = ws or wb.worksheets[0]

    hrow, cols, old = _find_header(ws)
    if not hrow:
        return {"rows": [], "header_row": None, "columns": [], "sheet": ws.title,
                "warnings": ["No column headed 'Plate' was found - is this the "
                             "right sheet?"]}
    if old:
        return {"rows": [], "header_row": hrow, "columns": sorted(cols), "sheet": ws.title,
                "warnings": [],
                "error": ("This file uses the old template (it has a %s column). Use the "
                          "new readiness template: Status holds FH, BH or the reason the "
                          "truck is not running, and Loaded / Empty is its own column. "
                          "Nothing was imported." % " / ".join(old))}

    warnings = []
    if "status" not in cols:
        warnings.append("No 'Status' column - FH / BH and reasons will be blank.")
    if "load" not in cols:
        warnings.append("No 'Loaded / Empty' column - that information will be blank.")
    if "arrive_time" not in cols:
        warnings.append("No 'Time arrive Mine' column - that information will be blank.")

    def texts(r, field):
        out = []
        for c in cols.get(field, []):
            v = ws.cell(row=r, column=c).value
            if v is not None and str(v).strip() != "":
                out.append(str(v).strip())
        return out

    def first(r, field):
        for c in cols.get(field, []):
            v = ws.cell(row=r, column=c).value
            if v is not None and str(v).strip() != "":
                return v
        return None

    def text(r, field):
        t = texts(r, field)
        return t[0] if t else ""

    rows, seen, misplaced = [], {}, []
    for r in range(hrow + 1, ws.max_row + 1):
        raw = first(r, "plate")
        if raw is None or not PLATE_RE.match(str(raw)):
            continue
        key = norm_plate(raw)
        if not key:
            continue
        if key in seen:
            warnings.append("%s appears more than once - the later row was used."
                            % str(raw).strip())

        status = text(r, "status")
        if load_word(status):
            # Loaded / Empty written where the leg or reason belongs. Not guessed
            # into anything: left blank, and said so.
            misplaced.append(str(raw).strip())
            status = ""
        activity = leg_word(status) or status
        load_raw = text(r, "load")

        rec = {
            "plate": str(raw).strip(),
            "key": key,
            "location": text(r, "location"),
            "status": load_word(load_raw) or load_raw,
            "activity": activity,
            "arrive_time": _as_hhmm(first(r, "arrive_time")),
            "arrive_date": _as_date(first(r, "arrive_date")),
            "back_in_service": _as_date(first(r, "back_in_service")),
            "remark": " · ".join(texts(r, "remark")),
            "row": r,
        }
        seen[key] = rec
        rows.append(rec)

    if misplaced:
        warnings.append("%d truck(s) have Loaded or Empty in the Status column (%s%s). "
                        "Status is FH, BH or the reason; Loaded / Empty has its own "
                        "column. Their status was left blank."
                        % (len(misplaced), ", ".join(misplaced[:5]),
                           "..." if len(misplaced) > 5 else ""))

    # later row wins on duplicates
    rows = list({r["key"]: r for r in rows}.values())
    return {"rows": rows, "header_row": hrow, "columns": sorted(cols),
            "sheet": ws.title, "warnings": warnings}


# Words that mean the truck is NOT available to run today. Matched as substrings,
# because subcontractors write sentences, not values: a real sheet carried
# "Unloading -> Maintenace -> 06/06 back to Mine", which an exact match treated as
# a working truck. The misspelling is deliberate - it is what they actually send.
NOT_RUNNING = ("maintenance", "maintenace", "maintainance", "not available",
               "standby", "stand by", "breakdown", "break down", "repair",
               "workshop", "garage",
               # Added with the drop-down: every value it offers must be
               # recognised, or a truck picked as out of service would still be
               # planned a load. Phrases, not single words, so ordinary remarks
               # do not trip them.
               "accident", "no driver", "paperwork")


def is_running(activity):
    a = str(activity or "").strip().lower()
    if not a:
        return True
    return not any(w in a for w in NOT_RUNNING)
