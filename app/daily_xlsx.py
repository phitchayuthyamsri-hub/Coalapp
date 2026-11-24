"""The Daily page as an Excel file, coloured like the page (24/11/2026).

The page sends what it has on screen - the period, the filters, both tables in
their on-screen order, and one row per truck per day - and this lays it out
with the page's own dark colours: the symbol colours, the status colours down
the left of the counts, the darker total and name columns. The browser's own
Excel library cannot write colours, which is why the file is built here.
"""
import io

from openpyxl import Workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

# The page's dark theme (app/tool/index.html :root and the Daily panel rules).
BG, PANEL, PANEL2, SUMBG, HEAD = "0E1418", "161E25", "1D272F", "1A2630", "0A1014"
INK, MUTED, LINE, DOW = "E6EDF3", "8B98A5", "2A343D", "AEB4BD"
SYM_COLOR = {"circle": "34D399", "half": "A78BFA", "wait": "2F6FDB", "cross": "F87171",
             "nogps": "9AA4B2", "square": "E0A93F"}
MANUAL, WB = "2DD4BF", "2E9BFF"
SYM = {"circle": "●", "half": "◐", "wait": "⏳", "cross": "✕", "nogps": "No GPS", "square": "■"}
WORD = {"circle": "Came as planned", "half": "Not as planned", "wait": "Waiting",
        "cross": "Did not come", "nogps": "No GPS", "square": "Came - not in plan"}
# Counts table: the row's field -> its colour (the page's statrow classes).
ROW_COLOR = {"planned": INK, "asPlanned": SYM_COLOR["circle"], "offPlan": SYM_COLOR["half"],
             "waiting": SYM_COLOR["wait"], "noShow": SYM_COLOR["cross"],
             "noGps": SYM_COLOR["nogps"], "unplan": SYM_COLOR["square"]}
SUM_KEYS = ["circle", "half", "wait", "cross", "nogps", "square"]
SUM_HEAD = ["●", "◐", "⏳", "✕", "No GPS", "■"]

_thin = Side(style="thin", color=LINE)
GRID = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
fill = lambda c: PatternFill("solid", fgColor=c)
CENTER = Alignment(horizontal="center", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center")


def _day_head(d):
    """2026-11-24 -> 'Tue\\n24 Nov', as the page heads its columns."""
    from datetime import datetime
    try:
        x = datetime.strptime(d, "%Y-%m-%d")
    except (TypeError, ValueError):
        return str(d)
    return "%s\n%d %s" % (x.strftime("%a"), x.day, x.strftime("%b"))


def _cell(ws, r, c, v, bg=PANEL, color=INK, bold=False, align=CENTER, size=10, font=None):
    x = ws.cell(row=r, column=c, value=v)
    x.fill = fill(bg)
    x.font = Font(name=font or "Segoe UI", size=size, bold=bold, color=color)
    x.alignment = align
    x.border = GRID
    return x


def _head_row(ws, r, labels, colors=None):
    for i, lab in enumerate(labels, 1):
        x = _cell(ws, r, i, lab, bg=HEAD, color=(colors or {}).get(i, "FFFFFF"), bold=True, size=9)
        x.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[r].height = 30


def _title(ws, text, sub):
    ws.sheet_properties.tabColor = "2DD4BF"
    ws.sheet_view.showGridLines = False
    ws.cell(row=1, column=1, value=text).font = Font(name="Segoe UI", size=13, bold=True, color="0A1014")
    ws.cell(row=2, column=1, value=sub).font = Font(name="Segoe UI", size=9, italic=True, color="5B6670")


def build(d):
    """d: what the page sends (see exportDailyXlsx in app/tool/index.html). -> bytes"""
    dates = d.get("dates") or []
    period = "%s to %s" % (d.get("from") or "", d.get("to") or "")
    sub = "Period %s · Fleet: %s · Subcontractor: %s · exported %s" % (
        period, d.get("scope") or "", d.get("company") or "All", d.get("exported") or "")
    wb = Workbook()

    # ── 1. Daily status counts ───────────────────────────────────────────────
    ws = wb.active
    ws.title = "Daily status counts"
    _title(ws, "Daily status counts", sub)
    _head_row(ws, 4, ["Status / Date", "Total"] + [_day_head(x) for x in dates])
    r = 5
    for row in d.get("counts") or []:
        col = ROW_COLOR.get(row.get("f"), INK)
        x = _cell(ws, r, 1, row.get("label"), bg=PANEL2, bold=True, align=LEFT)
        if row.get("f") != "planned":
            x.border = Border(left=Side(style="thick", color=col), right=_thin, top=_thin, bottom=_thin)
        _cell(ws, r, 2, row.get("total") or None, bg=SUMBG, color=col, bold=True)
        for i, v in enumerate(row.get("vals") or [], 3):
            _cell(ws, r, i, v or None, bg=PANEL, color=col, bold=True)
        r += 1
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 9
    for i in range(len(dates)):
        ws.column_dimensions[ws.cell(row=4, column=3 + i).column_letter].width = 8
    ws.freeze_panes = "C5"

    # ── 2. Per-truck daily symbols ───────────────────────────────────────────
    ws = wb.create_sheet("Per-truck symbols")
    _title(ws, "Per-truck daily symbols", sub)
    heads = ["Truck / Date", "Subcontractor"] + SUM_HEAD + [_day_head(x) for x in dates]
    _head_row(ws, 4, heads, {3 + i: SYM_COLOR[k] for i, k in enumerate(SUM_KEYS)})
    r = 5
    for g in d.get("grid") or []:
        plate = g.get("plate") or ""
        if g.get("wb"):
            v = CellRichText(TextBlock(InlineFont(rFont="Consolas", sz=10, b=True, color=INK), plate),
                             TextBlock(InlineFont(rFont="Segoe UI", sz=8, b=True, color=WB), "  ⚠ WB"))
            _cell(ws, r, 1, v, bg=PANEL2, align=LEFT)
        else:
            _cell(ws, r, 1, plate, bg=PANEL2, bold=True, align=LEFT, font="Consolas")
        _cell(ws, r, 2, g.get("sub") or "", bg=PANEL2, color="C9D1D9", bold=True, align=LEFT, size=9)
        tot = g.get("totals") or {}
        for i, k in enumerate(SUM_KEYS, 3):
            _cell(ws, r, i, tot.get(k) or None, bg=SUMBG, color=SYM_COLOR[k], bold=True)
        for i, c in enumerate(g.get("cells") or [], 3 + len(SUM_KEYS)):
            if not c:
                _cell(ws, r, i, None)
                continue
            parts = []
            if c.get("sym"):
                parts.append(TextBlock(InlineFont(rFont="Segoe UI Symbol", sz=11 if c["sym"] != "nogps" else 8,
                                                  b=c["sym"] == "nogps", color=SYM_COLOR.get(c["sym"], INK)),
                                       SYM.get(c["sym"], "")))
            if c.get("man"):
                parts.append(TextBlock(InlineFont(rFont="Segoe UI Symbol", sz=10, color=MANUAL), " ◆"))
            if c.get("wb"):
                parts.append(TextBlock(InlineFont(rFont="Segoe UI Symbol", sz=10, color=WB), " ⚠"))
            if c.get("note"):
                parts.append(TextBlock(InlineFont(rFont="Segoe UI", sz=7, color=MUTED), " " + str(c["note"])))
            _cell(ws, r, i, CellRichText(*parts) if parts else None)
        r += 1
    ws.column_dimensions["A"].width = 15
    ws.column_dimensions["B"].width = 14
    for i in range(len(SUM_KEYS)):
        ws.column_dimensions[ws.cell(row=4, column=3 + i).column_letter].width = 7
    for i in range(len(dates)):
        ws.column_dimensions[ws.cell(row=4, column=3 + len(SUM_KEYS) + i).column_letter].width = 8
    ws.freeze_panes = ws.cell(row=5, column=3 + len(SUM_KEYS))

    # ── 3. One row per truck per day ─────────────────────────────────────────
    ws = wb.create_sheet("Per truck per day")
    _title(ws, "One row per truck per day", sub)
    # No hours-off column (24/11/2026): "not as planned" is its icon in the file.
    _head_row(ws, 4, ["Date", "Truck", "Subcontractor", "Status", "Manual", "Weighbridge", "Details"])
    r = 5
    for x in d.get("detail") or []:
        sym = x.get("sym") or ""
        _cell(ws, r, 1, x.get("date"), bg=PANEL2)
        _cell(ws, r, 2, x.get("plate"), bg=PANEL2, bold=True, font="Consolas")
        _cell(ws, r, 3, x.get("sub"), bg=PANEL2, color="C9D1D9", align=LEFT)
        _cell(ws, r, 4, ((SYM.get(sym, "") + "  ") if sym else "") + WORD.get(sym, ""),
              color=SYM_COLOR.get(sym, INK), bold=True, align=LEFT)
        _cell(ws, r, 5, "◆ yes" if x.get("man") else None, color=MANUAL)
        _cell(ws, r, 6, "⚠ yes" if x.get("wb") else None, color=WB)
        _cell(ws, r, 7, x.get("tip") or None, color=INK, align=LEFT, size=9)
        r += 1
    for col, w in zip("ABCDEFG", (11, 11, 14, 22, 8, 12, 90)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "C5"
    if r > 5:
        ws.auto_filter.ref = "A4:G%d" % (r - 1)

    # ── 4. About ─────────────────────────────────────────────────────────────
    ws = wb.create_sheet("About")
    _title(ws, "Daily performance", sub)
    legend = [("●", "circle", "Came as planned - at the mine within 1 h of the plan time"),
              ("◐", "half", "Not as planned - 1 to 12 h off the plan time"),
              ("⏳", "wait", "Waiting - the window is still open"),
              ("✕", "cross", "Did not come - no mine arrival within 12 h"),
              ("No GPS", "nogps", "No position for 12 h either side"),
              ("■", "square", "Came, not in plan")]
    _head_row(ws, 4, ["Symbol", "Meaning"])
    r = 5
    for s, k, text in legend:
        _cell(ws, r, 1, s, bg=PANEL2, color=SYM_COLOR[k], bold=True)
        _cell(ws, r, 2, text, align=LEFT)
        r += 1
    _cell(ws, r, 1, "◆", bg=PANEL2, color=MANUAL, bold=True)
    _cell(ws, r, 2, "Manual loading time - not scored", align=LEFT)
    _cell(ws, r + 1, 1, "⚠", bg=PANEL2, color=WB, bold=True)
    _cell(ws, r + 1, 2, "Mine time from the weighbridge (GPS error)", align=LEFT)
    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["B"].width = 80

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
