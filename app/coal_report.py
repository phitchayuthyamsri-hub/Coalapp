"""The Daily/Weekly performance report's own data (11/11/2026).

Three data lists, named after the sheets of the team's "Calculation file":

  1. Input_Actual data loading - one row per weighbridge ticket (CoalRptWeigh)
  2. Truck readiness           - one row per truck registration (CoalRptReady)
  3. Contract                  - the contract list (shared store, small)

Each list is filled from the team's own files as they are: the Calculation
file itself, or the daily exports it is built from (the weighbridge ticket
export and the Registration Trucklist export). A file is the record for the
days it covers - those days are replaced, the others are kept - so the same
daily export can be uploaded again after a correction.

The workbooks are read straight from their XML, one row at a time, so a
100 MB Calculation file does not have to be held in memory.
"""
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta

from sqlalchemy import func

from .models import db, CoalRptWeigh, CoalRptReady

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
EXCEL_EPOCH = datetime(1899, 12, 30)


# ── reading an xlsx, one sheet, row by row ───────────────────────────────────
def _col_index(ref):
    n = 0
    for ch in ref:
        if "A" <= ch <= "Z":
            n = n * 26 + ord(ch) - 64
        else:
            break
    return n - 1


def sheet_names(z):
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = {r.get("Id"): r.get("Target") for r in rels}
    out = []
    for s in wb.iter(NS + "sheet"):
        t = target.get(s.get(RNS + "id"), "")
        t = t.lstrip("/")
        if not t.startswith("xl/"):
            t = "xl/" + t
        out.append((s.get("name"), t))
    return out


def _shared_strings(z):
    try:
        f = z.open("xl/sharedStrings.xml")
    except KeyError:
        return []
    out = []
    for ev, el in ET.iterparse(f, events=("end",)):
        if el.tag == NS + "si":
            out.append("".join(t.text or "" for t in el.iter(NS + "t")))
            el.clear()
    return out


def iter_rows(z, path, sst):
    """Each row of a sheet as a list of raw values (str or float), gaps as None."""
    with z.open(path) as f:
        for ev, el in ET.iterparse(f, events=("end",)):
            if el.tag != NS + "row":
                continue
            row = []
            for c in el.iter(NS + "c"):
                i = _col_index(c.get("r", "")) if c.get("r") else len(row)
                t = c.get("t")
                v = c.find(NS + "v")
                if t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(NS + "t"))
                elif v is None or v.text is None:
                    val = None
                elif t == "s":
                    try:
                        val = sst[int(v.text)]
                    except (ValueError, IndexError):
                        val = None
                elif t in ("str", "e"):
                    val = v.text
                elif t == "b":
                    val = v.text == "1"
                else:
                    try:
                        val = float(v.text)
                    except ValueError:
                        val = v.text
                while len(row) < i:
                    row.append(None)
                row.append(val)
            el.clear()
            yield row


def _norm(h):
    return re.sub(r"[^a-z0-9]", "", str(h or "").lower())


def _s(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _day(v):
    """A date cell -> 'YYYY-MM-DD'; '' when it is not a believable date."""
    d = None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if 20000 < v < 80000:                          # 1954..2119
            d = (EXCEL_EPOCH + timedelta(days=float(v))).date()
    elif isinstance(v, datetime):
        d = v.date()
    elif isinstance(v, date):
        d = v
    else:
        s = _s(v).split(" ")[0].split("T")[0]
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
            try:
                d = datetime.strptime(s, fmt).date()
                break
            except ValueError:
                pass
    if d is None or d.year < 2015:
        return ""
    return d.isoformat()


def _minutes(v):
    """A time cell -> minutes after midnight, or None."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        frac = float(v) % 1
        return int(round(frac * 1440)) % 1440
    m = re.search(r"(\d{1,2}):(\d{2})", str(v))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _num(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def norm_plate(s):
    return re.sub(r"[\s.\-_/\\]", "", str(s or "")).upper()


# ── finding each list's sheet and header row ─────────────────────────────────
# name of the sheet in the Calculation file, and the headers that identify the
# same table in a daily export
KINDS = {
    "weigh": {"sheet": "input_actual data loading",
              "need": ("truckno", "netweight", "dateout")},
    "ready": {"sheet": "truck readiness",
              "need": ("id", "registerdate", "truckplate")},
    "contracts": {"sheet": "contract",
                  "need": ("customername", "start", "end")},
}
CONTRACT_KEY = ("contract", "contractno", "contrat", "contratno")


def _header_map(row):
    return {_norm(h): i for i, h in reversed(list(enumerate(row))) if _norm(h)}


def _find(z, kind, sst_holder):
    """(sheet name, header map, row iterator positioned after the header)."""
    spec = KINDS[kind]
    names = sheet_names(z)
    # the Calculation file's own sheet first, then any sheet with the headers
    order = sorted(names, key=lambda nt: 0 if nt[0].strip().lower() == spec["sheet"] else 1)
    for name, path in order:
        if sst_holder[0] is None:
            sst_holder[0] = _shared_strings(z)
        it = iter_rows(z, path, sst_holder[0])
        for _ in range(8):                        # the header is in the first rows
            try:
                row = next(it)
            except StopIteration:
                break
            H = _header_map(row)
            if all(k in H for k in spec["need"]) and (kind != "contracts" or any(k in H for k in CONTRACT_KEY)):
                return name, H, it
    return None, None, None


def _open(fileobj):
    """A path, or a seekable file (an upload is spooled to disk); read in place."""
    try:
        return zipfile.ZipFile(fileobj)
    except zipfile.BadZipFile:
        raise ValueError("not an .xlsx file")


# ── parsing ──────────────────────────────────────────────────────────────────
def _stamp(dv, tv):
    """Date cell + time cell -> datetime, or None."""
    d = _day(dv)
    if not d:
        return None
    m = _minutes(tv) or 0
    return datetime.strptime(d, "%Y-%m-%d") + timedelta(minutes=m)


def loading_day(dt):
    """The team's loading day and half (Calculation file, columns AN and AP):
    Date = INT(Date Out + Time Out - 6 h), AM/PM = TEXT(the same, "AM/PM") -
    a day runs 06:00 to 06:00, AM = 06:00-18:00, PM = 18:00-06:00."""
    s = dt - timedelta(hours=6)
    return s.date().isoformat(), ("d" if s.hour < 12 else "n")


def parse_weigh(H, rows):
    """Yields one ticket at a time."""
    g = lambda r, *ks: next((r[H[k]] for k in ks if k in H and H[k] < len(r)), None)
    for r in rows:
        plate_raw = _s(g(r, "truckno"))
        if not plate_raw:
            continue
        t_out = _stamp(g(r, "dateout"), g(r, "timeout"))
        t_in = _stamp(g(r, "datein"), g(r, "timein"))
        ref = t_out or t_in
        if not ref:
            continue
        day, ap = loading_day(ref)
        net = _num(g(r, "netweight"))
        tons = round(net / 1000.0, 3) if net > 300 else round(net, 3)      # kg on the ticket
        tid = _s(g(r, "ticketid")) or ("W" + _s(g(r, "wid")))
        if tid in ("", "W"):
            tid = "%s|%s|%s" % (ref.isoformat(), norm_plate(plate_raw), net)
        yield {"id": tid[:40], "day": day, "ap": ap,
                    "day_in": (t_in or ref).date().isoformat(),   # gate-in date: the register match's second try
                    "plate": norm_plate(plate_raw)[:32], "plate_raw": plate_raw[:40], "net_t": tons,
                    "contract": _s(g(r, "contractno", "contract", "contratno"))[:120],
                    "customer": _s(g(r, "customername"))[:160],
                    "market": _market(_s(g(r, "ovsdmt", "export", "exportoversea")))}


def _market(s):
    u = s.upper()
    if re.search(r"OVS|OVER|EXPORT", u):
        return "Oversea"
    if re.search(r"DMT|DOMES|LOCAL", u):
        return "Domestic"
    return s[:16]


def parse_ready(H, rows):
    """Yields one registration at a time."""
    g = lambda r, *ks: next((r[H[k]] for k in ks if k in H and H[k] < len(r)), None)
    for r in rows:
        rid = _s(g(r, "id"))
        plate_raw = _s(g(r, "truckplate"))
        day = _day(g(r, "registerdate"))
        if not rid or not plate_raw or not day:
            continue
        yield {"id": rid[:64], "reg_date": day, "contract": _s(g(r, "contractno"))[:120],
                    "plate": norm_plate(plate_raw)[:32], "plate_raw": plate_raw[:40],
                    "country": _s(g(r, "country"))[:30],
                    # the Calculation file spells it "Transportion Company"
                    "company": _s(g(r, "transportcompany", "transportioncompany"))[:80],
                    "sub": _s(g(r, "subcontractor"))[:80],
                    "status": _s(g(r, "registrationstatus"))[:30]}


def parse_contracts(H, rows):
    g = lambda r, *ks: next((r[H[k]] for k in ks if k in H and H[k] < len(r)), None)
    out = []
    for r in rows:
        c = _s(g(r, *CONTRACT_KEY))
        cust = _s(g(r, "customername"))
        if not c or not cust:
            continue
        out.append({"customer": cust, "customerFull": _s(g(r, "customernamefull")),
                    "export": _market(_s(g(r, "export", "exportoversea"))), "term": _s(g(r, "term")),
                    "endUser": _s(g(r, "enduser")), "contract": c,
                    "start": _day(g(r, "start")), "end": _day(g(r, "end")),
                    "extension": _day(g(r, "extension")), "gar": _s(g(r, "gartype", "gar")),
                    "transporter": _s(g(r, "transporter")), "qty": _num(g(r, "cntqty", "qty", "quantity")),
                    "tonPerTrip": _num(g(r, "tontrp", "tontrip")), "status": _s(g(r, "status"))})
    return out


# ── storing ──────────────────────────────────────────────────────────────────
def _store(model, col, rows, chunk=2000):
    """The file is the record for the days it covers: its rows are written (a
    ticket already stored is replaced, wherever it was), then any row of those
    days the file no longer has is removed. Written in batches as read; one
    transaction, so a file that fails half way leaves nothing behind."""
    ins = model.__table__.insert().prefix_with("OR REPLACE")
    days, ids, buf = set(), set(), []
    try:
        for r in rows:
            days.add(r[col])
            ids.add(r["id"])
            buf.append(r)
            if len(buf) >= chunk:
                db.session.execute(ins, buf)
                buf = []
        if buf:
            db.session.execute(ins, buf)
        dl = sorted(days)
        for i in range(0, len(dl), 200):
            gone = [x for (x,) in db.session.query(model.id).filter(getattr(model, col).in_(dl[i:i + 200]))
                    if x not in ids]
            for j in range(0, len(gone), 500):
                model.query.filter(model.id.in_(gone[j:j + 500])).delete(synchronize_session=False)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return len(ids), (dl[0] if dl else None), (dl[-1] if dl else None)


def import_workbook(fileobj, kinds=("weigh", "ready", "contracts"), log=None):
    """Read the wanted lists from one workbook and store them.

    Returns {kind: {"rows", "from", "to", "sheet"}} for each list found, and
    {"missing": [...]} for those the workbook does not hold. Contracts are
    returned as data (they live in the shared store; the caller saves them)."""
    z = _open(fileobj)
    sst = [None]
    res = {"missing": []}
    for kind in kinds:
        name, H, it = _find(z, kind, sst)
        if not it:
            res["missing"].append(kind)
            continue
        if log:
            log("%s: reading sheet %r" % (kind, name))
        if kind == "weigh":
            n, lo, hi = _store(CoalRptWeigh, "day", parse_weigh(H, it))
            res[kind] = {"rows": n, "from": lo, "to": hi, "sheet": name}
        elif kind == "ready":
            n, lo, hi = _store(CoalRptReady, "reg_date", parse_ready(H, it))
            res[kind] = {"rows": n, "from": lo, "to": hi, "sheet": name}
        else:
            rows = parse_contracts(H, it)
            res[kind] = {"rows": len(rows), "sheet": name, "data": rows}
        if log:
            log("%s: %s" % (kind, {k: v for k, v in res[kind].items() if k != "data"}))
    return res


# ── what the page reads ──────────────────────────────────────────────────────
def summary():
    out = {}
    for kind, model, col in (("weigh", CoalRptWeigh, "day"), ("ready", CoalRptReady, "reg_date")):
        c = getattr(model, col)
        n, lo, hi = db.session.query(func.count(model.id), func.min(c), func.max(c)).one()
        out[kind] = {"rows": n or 0, "from": lo, "to": hi}
    return out


def report_data(days=120):
    """Rows of the last `days` days (up to the newest ticket) in a compact form,
    plus every contract's tons and trips to date over the whole history."""
    S = summary()
    hi = S["weigh"]["to"] or S["ready"]["to"]
    since = (datetime.strptime(hi, "%Y-%m-%d").date() - timedelta(days=days)).isoformat() if hi else "0000"
    dic = {"c": [], "p": [], "cust": [], "co": [], "sub": []}
    idx = {k: {} for k in dic}

    def ix(k, v):
        m = idx[k]
        if v not in m:
            m[v] = len(dic[k])
            dic[k].append(v)
        return m[v]

    w = []
    for r in db.session.query(CoalRptWeigh.day, CoalRptWeigh.plate, CoalRptWeigh.net_t, CoalRptWeigh.contract,
                              CoalRptWeigh.customer, CoalRptWeigh.market, CoalRptWeigh.ap, CoalRptWeigh.day_in) \
            .filter(CoalRptWeigh.day >= since).order_by(CoalRptWeigh.day):
        w.append([r[0], ix("p", r[1]), round(r[2] or 0, 2), ix("c", r[3] or ""), ix("cust", r[4] or ""),
                  {"Oversea": 1, "Domestic": 2}.get(r[5], 0), 1 if r[6] == "n" else 0,
                  "" if not r[7] or r[7] == r[0] else r[7]])
    rr = []
    for r in db.session.query(CoalRptReady.reg_date, CoalRptReady.plate, CoalRptReady.contract,
                              CoalRptReady.company, CoalRptReady.sub) \
            .filter(CoalRptReady.reg_date >= since).order_by(CoalRptReady.reg_date):
        rr.append([r[0], ix("p", r[1]), ix("c", r[2] or ""), ix("co", r[3] or ""), ix("sub", r[4] or "")])
    totals = {}
    for c, t, n, last in db.session.query(CoalRptWeigh.contract, func.sum(CoalRptWeigh.net_t),
                                          func.count(CoalRptWeigh.id), func.max(CoalRptWeigh.day)) \
            .group_by(CoalRptWeigh.contract):
        totals[(c or "").strip().upper()] = {"t": round(t or 0, 2), "n": n, "last": last}
    return {"since": since, "dict": dic, "w": w, "r": rr, "totals": totals, "summary": S}


def list_rows(kind, q="", page=0, size=200):
    """One page of a data list, newest first, for the Data tab."""
    model, col = (CoalRptWeigh, "day") if kind == "weigh" else (CoalRptReady, "reg_date")
    qry = model.query
    q = (q or "").strip()
    if q:
        like = "%" + q + "%"
        fields = ([CoalRptWeigh.plate_raw, CoalRptWeigh.contract, CoalRptWeigh.customer, CoalRptWeigh.id, CoalRptWeigh.day]
                  if kind == "weigh" else
                  [CoalRptReady.plate_raw, CoalRptReady.contract, CoalRptReady.company, CoalRptReady.sub, CoalRptReady.reg_date])
        qp = norm_plate(q)
        conds = [f.ilike(like) for f in fields]
        if qp:
            conds.append(model.plate.like("%" + qp + "%"))
        qry = qry.filter(db.or_(*conds))
    total = qry.count()
    rows = qry.order_by(getattr(model, col).desc(), model.id).offset(page * size).limit(size).all()
    if kind == "weigh":
        data = [{"id": r.id, "day": r.day, "ap": r.ap, "plate": r.plate_raw, "net": r.net_t, "contract": r.contract,
                 "customer": r.customer, "market": r.market} for r in rows]
    else:
        data = [{"id": r.id, "day": r.reg_date, "plate": r.plate_raw, "contract": r.contract, "country": r.country,
                 "company": r.company, "sub": r.sub, "status": r.status} for r in rows]
    return {"total": total, "page": page, "size": size, "rows": data}
