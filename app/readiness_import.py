# -*- coding: utf-8 -*-
"""Read a subcontractor's daily readiness sheet.

Tolerant on purpose: subcontractors send their own layouts. Rather than demand
the exact template, find the header row by looking for a Plate column, then map
whatever columns are present. A sheet that predates the template still imports -
it just carries less information.

Two layouts are in use, and both must land in the same two fields:

  Bac Nam template   Leg (FH/BH) · Status (Loaded/Empty) · Activity (the reason)
  newer layout       Status (FH / BH / the reason) · Loaded / Empty

The system's `activity` carries the leg while a truck is working and the reason
when it is not; `status` carries the load state. The importer used to map Leg,
Status and Activity all onto `activity`, the last column (usually a blank
Activity) overwrote the other two, and a whole uploaded sheet arrived with no leg
and no load. So columns are now collected rather than overwritten, and a column
headed Status is read by what is IN it: a load word is the load, anything else is
the leg or the reason.
"""
import re
from datetime import datetime, time

from openpyxl import load_workbook

# header text -> which raw column it is. Lowercased, punctuation stripped, before
# match. Several headers may land on the same raw column; all are kept, in order.
HEADER_MAP = {
    "no": "no", "stt": "no",
    "plate": "plate", "licenseplate": "plate", "bienso": "plate", "truck": "plate",
    "location": "location", "vitri": "location",
    # FH or BH, in a column of its own (the Bac Nam template).
    "leg": "leg", "fhbh": "leg", "haul": "leg",
    # A column headed Status means different things in different layouts - the
    # load state in the Bac Nam template, the leg or reason in the newer one - so
    # it is classified value by value, not by its header.
    "status": "status_col", "trangthai": "status_col", "truckstatus": "status_col",
    # The reason a truck is not running, or a free note.
    "notrunningreason": "reason", "notrunning": "reason",
    "unavailablereason": "reason", "downtimereason": "reason",
    "reason": "reason", "lydo": "reason",
    "activity": "reason", "note": "reason", "ghichu": "reason",
    # The load state, which is what DailyListRow.sheet_status was always
    # documented as holding.
    "loadedempty": "load", "loadempty": "load", "loadedorempty": "load",
    "loadstatus": "load", "cohang": "load",
    "timearrivemine": "arrive_time", "timearrivalmine": "arrive_time",
    "arrivetime": "arrive_time", "giodenmo": "arrive_time",
    # older BBC sheets head these columns "Arrive Mine" / "Entry Mine Date"
    "arrivemine": "arrive_time", "arrivalmine": "arrive_time",
    "datearrivemine": "arrive_date", "datearrivalmine": "arrive_date",
    "arrivedate": "arrive_date", "ngaydenmo": "arrive_date",
    "entryminedate": "arrive_date", "entrymine": "arrive_date",
    "backinservice": "back_in_service", "remark": "remark", "remarks": "remark",
}

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

    -> (row, {raw column: [column numbers, in sheet order]})"""
    for r in range(1, min(ws.max_row, limit) + 1):
        cols = {}
        for c in range(1, min(ws.max_column, 20) + 1):
            f = HEADER_MAP.get(_norm_header(ws.cell(row=r, column=c).value))
            if f:
                cols.setdefault(f, []).append(c)
        if "plate" in cols:
            return r, cols
    return None, {}


def parse(path):
    """-> {'rows': [...], 'header_row': n, 'columns': [...], 'warnings': [...]}"""
    wb = load_workbook(path, data_only=True)
    ws = None
    for name in ("Readiness", "Sheet1"):
        if name in wb.sheetnames:
            ws = wb[name]
            break
    ws = ws or wb.worksheets[0]

    hrow, cols = _find_header(ws)
    warnings = []
    if not hrow:
        return {"rows": [], "header_row": None, "columns": [], "sheet": ws.title,
                "warnings": ["No column headed 'Plate' was found - is this the "
                             "right sheet?"]}

    if "arrive_time" not in cols:
        warnings.append("No 'Time arrive Mine' column - that information will be blank.")
    if not any(cols.get(f) for f in ("leg", "status_col", "reason")):
        warnings.append("No 'Status' or 'Leg' column - FH / BH and reasons will be blank.")

    def first(r, field):
        """The first non-blank cell among the columns mapped to `field`."""
        for c in cols.get(field, []):
            v = ws.cell(row=r, column=c).value
            if v is not None and str(v).strip() != "":
                return v
        return None

    def text(r, field):
        return str(first(r, field) or "").strip()

    rows, seen, any_load = [], {}, False
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

        leg = leg_word(first(r, "leg")) or text(r, "leg")
        status_raw = text(r, "status_col")
        reason = text(r, "reason")
        load_raw = text(r, "load")
        load = load_word(load_raw) or load_raw

        # The Bac Nam template: a Status cell holding a load word is the load.
        if load_word(status_raw):
            load = load or load_word(status_raw)
            status_raw = ""
        if leg_word(status_raw):
            status_raw = leg_word(status_raw)

        # One field carries both answers. A reason the truck cannot run wins,
        # wherever it was written; otherwise the leg, then a Status that was not a
        # load word, then whatever the Activity column said.
        blocker = next((t for t in (reason, status_raw) if t and not is_running(t)), "")
        activity = blocker or leg or status_raw or reason

        # Nothing they wrote is dropped: words that did not become the status go
        # to the remark, after their own.
        leftover = [t for t in (status_raw, reason) if t and t != activity]
        remark = " · ".join([x for x in [text(r, "remark")] + leftover if x])

        any_load = any_load or bool(load)
        rec = {
            "plate": str(raw).strip(),
            "key": key,
            "location": text(r, "location"),
            "status": load,
            "activity": activity,
            "arrive_time": _as_hhmm(first(r, "arrive_time")),
            "arrive_date": _as_date(first(r, "arrive_date")),
            "back_in_service": _as_date(first(r, "back_in_service")),
            "remark": remark,
            "row": r,
        }
        seen[key] = rec
        rows.append(rec)

    if rows and not any_load:
        warnings.append("No 'Loaded / Empty' column - that information will be blank.")

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
