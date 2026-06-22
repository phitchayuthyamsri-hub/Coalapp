"""
Core analytics engine — Python port of the original offline-HTML JS engine.

Pipeline:  GPS pings + anchors  ->  visits  ->  sequences (cycles)  ->  status rows
ETA uses operating-window gates on the QL49 corridor.

Everything here is pure / stateless: functions take data in, return data out.
The Flask layer loads rows from the DB, passes them here, and serves the result.
"""
import math
import re
from datetime import datetime, timedelta

# ── Plate normalization ──────────────────────────────────────────────────────
def norm_plate(p):
    return str(p or "").strip().upper()

def norm_plate_strict(p):
    """A-Z/0-9 only; must contain a Latin letter (excludes Lao-script plates)."""
    s = re.sub(r"[^A-Z0-9]", "", str(p or "").upper())
    return s if re.search(r"[A-Z]", s) else ""

# ── Geometry ─────────────────────────────────────────────────────────────────
def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    rad = math.radians
    d_lat = rad(lat2 - lat1)
    d_lng = rad(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(d_lng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def point_in_polygon(lat, lng, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        yi, xi = poly[i][0], poly[i][1]
        yj, xj = poly[j][0], poly[j][1]
        if ((yi > lat) != (yj > lat)) and \
           (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside

def polygon_centroid(poly):
    lat = sum(p[0] for p in poly) / len(poly)
    lng = sum(p[1] for p in poly) / len(poly)
    return [lat, lng]

def _to_xy(lat, lng, ref_lat):
    R = 6371.0
    x = math.radians(lng) * math.cos(math.radians(ref_lat)) * R
    y = math.radians(lat) * R
    return x, y

def _proj_on_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    len2 = dx * dx + dy * dy
    t = ((px - ax) * dx + (py - ay) * dy) / len2 if len2 else 0.0
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return t, math.hypot(px - cx, py - cy)

def remaining_km_along_route(points, lat, lng):
    """Remaining km from the snapped position to the END of the polyline."""
    if not points or len(points) < 2:
        return None
    px, py = _to_xy(lat, lng, lat)
    best = (0, 0.0, float("inf"))  # seg_idx, t, dist
    for i in range(1, len(points)):
        ax, ay = _to_xy(points[i - 1][0], points[i - 1][1], lat)
        bx, by = _to_xy(points[i][0], points[i][1], lat)
        t, dist = _proj_on_seg(px, py, ax, ay, bx, by)
        if dist < best[2]:
            best = (i, t, dist)
    seg_idx, t, _ = best
    seg_start, seg_end = points[seg_idx - 1], points[seg_idx]
    seg_len = haversine_km(seg_start[0], seg_start[1], seg_end[0], seg_end[1])
    rem = seg_len * (1 - t)
    for i in range(seg_idx + 1, len(points)):
        rem += haversine_km(points[i - 1][0], points[i - 1][1],
                            points[i][0], points[i][1])
    return rem

def remaining_and_snap(points, lat, lng):
    if not points or len(points) < 2:
        return None
    px, py = _to_xy(lat, lng, lat)
    best = (0, 0.0, float("inf"))
    for i in range(1, len(points)):
        ax, ay = _to_xy(points[i - 1][0], points[i - 1][1], lat)
        bx, by = _to_xy(points[i][0], points[i][1], lat)
        t, dist = _proj_on_seg(px, py, ax, ay, bx, by)
        if dist < best[2]:
            best = (i, t, dist)
    seg_idx, t, snap = best
    seg_start, seg_end = points[seg_idx - 1], points[seg_idx]
    rem = haversine_km(seg_start[0], seg_start[1], seg_end[0], seg_end[1]) * (1 - t)
    for i in range(seg_idx + 1, len(points)):
        rem += haversine_km(points[i - 1][0], points[i - 1][1],
                            points[i][0], points[i][1])
    return {"rem": rem, "snap_km": snap}

# ── Distance legs (fronthaul / backhaul spine) ───────────────────────────────
DIST_LEGS = [
    {"key": "mine_border",    "label": "Mine \u2192 Border",            "from": "xppl",   "to": "border"},
    {"key": "border_ql49b",   "label": "Border \u2192 QL49(Border)",    "from": "border", "to": "ql49b"},
    {"key": "ql49b_ql49p",    "label": "QL49(Border) \u2192 QL49(Port)","from": "ql49b",  "to": "ql49p"},
    {"key": "ql49p_port",     "label": "QL49(Port) \u2192 Port",        "from": "ql49p",  "to": "port"},
    {"key": "port_mine",      "label": "Port \u2192 Mine (QL9)",        "from": "port",   "to": "xppl"},
    {"key": "port_mine_ql49", "label": "Port \u2192 Mine (via QL49)",   "from": "port",   "to": "xppl"},
]
FRONTHAUL_LEGS = ["mine_border", "border_ql49b", "ql49b_ql49p", "ql49p_port"]

# ── Operating-window ETA ─────────────────────────────────────────────────────
ETA_WINDOWS = {
    "border":  {"open": 15, "close": 17, "paperwork_hrs": 1},
    "ql49In":  {"open": 19, "close": 24},
    "port":    {"open": 7,  "close": 17},
    "ql49Out": {"open": 0,  "close": 5},
}

def push_into_window(dt, win):
    h = dt.hour + dt.minute / 60.0
    arrival = dt
    if h < win["open"]:
        arrival = dt.replace(hour=win["open"], minute=0, second=0, microsecond=0)
    elif h >= win["close"]:
        arrival = (dt + timedelta(days=1)).replace(
            hour=win["open"], minute=0, second=0, microsecond=0)
    if win.get("paperwork_hrs"):
        arrival = arrival + timedelta(hours=win["paperwork_hrs"])
    return arrival

def _km_to_anchor_along_leg(points, from_lat, from_lng, anchor_poly):
    if not points or not anchor_poly:
        return None
    clat, clng = polygon_centroid(anchor_poly)
    here = remaining_km_along_route(points, from_lat, from_lng)
    there = remaining_km_along_route(points, clat, clng)
    if here is None or there is None:
        return None
    d = here - there
    return d if d > 0 else None

def constraint_aware_eta(start_time, points, lat, lng, speed, haul,
                         backhaul_type=None, role_polys=None):
    """
    Walk remaining gates in haul order, pushing past each closed window.
    role_polys: {role_id: polygon} for gate centroids on the active leg.
    Returns a datetime or None.
    """
    if not start_time or not points or not (speed and speed > 0):
        return None
    rem_total = remaining_km_along_route(points, lat, lng)
    if rem_total is None:
        return None
    role_polys = role_polys or {}

    def hop(km):
        return timedelta(hours=km / speed)

    t = start_time

    if haul == "Fronthaul":
        gates = [("border", ETA_WINDOWS["border"]),
                 ("ql49",   ETA_WINDOWS["ql49In"]),
                 ("port",   ETA_WINDOWS["port"])]
        for role, win in gates:
            poly = role_polys.get(role)
            if not poly:
                continue
            d = _km_to_anchor_along_leg(points, lat, lng, poly)
            if d is None:
                continue
            t = t + hop(d)
            t = push_into_window(t, win)
        return t

    if haul == "Backhaul":
        poly = role_polys.get("ql49b") or role_polys.get("ql49")
        if poly:
            d = _km_to_anchor_along_leg(points, lat, lng, poly)
            if d is not None:
                t_exit = t + hop(d)
                h = t_exit.hour + t_exit.minute / 60.0
                if h >= ETA_WINDOWS["ql49Out"]["close"]:
                    t_exit = (t_exit + timedelta(days=1)).replace(
                        hour=0, minute=0, second=0, microsecond=0)
                rem_from_exit = rem_total - d
                return t_exit + hop(rem_from_exit if rem_from_exit > 0 else 0)
        return t + hop(rem_total)

    return None

# ── Visit detection ──────────────────────────────────────────────────────────
def build_visits(pings, anchors, deactivated=None):
    """
    pings:   [{plate, dt(datetime), lat, lng, speed, status}]
    anchors: [{id, name, polygon, min_dwell_min}]
    Returns visits: [{plate, anchor_id, anchor_name, visit_num, enter, exit, open, ping_count}]
    """
    deactivated = deactivated or set()
    out = []
    if not pings or not anchors:
        return out
    by_plate = {}
    for p in pings:
        if norm_plate(p["plate"]) in deactivated:
            continue
        by_plate.setdefault(p["plate"], []).append(p)

    for plate, plist in by_plate.items():
        plist.sort(key=lambda x: x["dt"])
        for anchor in anchors:
            min_ms = (anchor.get("min_dwell_min", 5) or 0) * 60000
            inside_prev = False
            current = None
            visit_count = 0
            prev_ping = None
            for ping in plist:
                inside_now = point_in_polygon(ping["lat"], ping["lng"], anchor["polygon"])
                if not inside_prev and inside_now:
                    visit_count += 1
                    current = {"plate": plate, "anchor_id": anchor["id"],
                               "anchor_name": anchor["name"], "visit_num": visit_count,
                               "enter": ping["dt"], "exit": None, "open": False,
                               "pings_inside": [ping]}
                elif inside_prev and inside_now:
                    if current:
                        current["pings_inside"].append(ping)
                elif inside_prev and not inside_now:
                    if current:
                        current["exit"] = prev_ping["dt"] if prev_ping else ping["dt"]
                        dur = (current["exit"] - current["enter"]).total_seconds() * 1000
                        if not (min_ms > 0 and dur < min_ms):
                            out.append(current)
                        current = None
                inside_prev = inside_now
                prev_ping = ping
            if current:
                last_in = current["pings_inside"][-1]
                current["exit"] = last_in["dt"] if last_in else current["enter"]
                current["open"] = True
                dur = (current["exit"] - current["enter"]).total_seconds() * 1000
                if not (min_ms > 0 and dur < min_ms):
                    out.append(current)

    for v in out:
        v["ping_count"] = len(v.get("pings_inside", []))
        v.pop("pings_inside", None)
    out.sort(key=lambda v: v["enter"])
    for i, v in enumerate(out):
        v["no"] = i + 1
    return out

# ── Sequence / cycle builder (forward-walking state machine) ─────────────────
def recompute_sequences(visits, roles):
    """
    roles: {xppl, loading, border, ql49, port, detour, ql49b, ql49p -> anchor_id}
    Each XPPL visit opens a cycle; the next XPPL visit closes it.
    Returns sequences with the timing fields the status engine needs.
    """
    seqs = []
    xppl_id = roles.get("xppl")
    if not xppl_id:
        return seqs
    loading_id = roles.get("loading")
    border_id = roles.get("border")
    ql49_id = roles.get("ql49")
    port_id = roles.get("port")
    detour_id = roles.get("detour")

    by_plate = {}
    for v in visits:
        by_plate.setdefault(v["plate"], []).append(v)
    for arr in by_plate.values():
        arr.sort(key=lambda v: v["enter"])

    for plate, vlist in by_plate.items():
        xppl_visits = [v for v in vlist if v["anchor_id"] == xppl_id]
        if not xppl_visits:
            continue
        for i, start in enumerate(xppl_visits):
            nxt = xppl_visits[i + 1] if i + 1 < len(xppl_visits) else None
            cycle_end = nxt["enter"] if nxt else None
            c = {"plate": plate, "cycle_date": start["enter"],
                 "xppl_in": start["enter"], "xppl_out": start["exit"],
                 "loading_in": None, "loading_out": None,
                 "lalay_out_in": None, "lalay_out_out": None,
                 "ql49_out_in": None, "ql49_out_out": None,
                 "chan_may_in": None, "chan_may_out": None,
                 "ql49_back_in": None, "ql49_back_out": None,
                 "detour_in": None, "detour_out": None,
                 "lalay_back_in": None, "lalay_back_out": None,
                 "xppl_r": nxt["enter"] if nxt else None,
                 "backhaul_type": None}

            window = [v for v in vlist if v["enter"] >= start["enter"]
                      and (cycle_end is None or v["enter"] < cycle_end)]

            cursor = (start["exit"] or start["enter"])

            def find_after(anchor_id, cur):
                if not anchor_id:
                    return None
                for v in window:
                    if v["anchor_id"] == anchor_id and v["enter"] > cur:
                        return v
                return None

            # Loading (sub-zone of mine): search from cycle start
            if loading_id:
                load_v = next((v for v in window
                               if v["anchor_id"] == loading_id
                               and v["enter"] >= start["enter"]), None)
                if load_v:
                    c["loading_in"] = load_v["enter"]
                    c["loading_out"] = load_v["exit"]
                    load_end = load_v["exit"] or load_v["enter"]
                    if load_end > cursor:
                        cursor = load_end

            lo = find_after(border_id, cursor)
            if lo:
                c["lalay_out_in"], c["lalay_out_out"] = lo["enter"], lo["exit"]
                cursor = lo["exit"] or lo["enter"]
            qo = find_after(ql49_id, cursor)
            if qo:
                c["ql49_out_in"], c["ql49_out_out"] = qo["enter"], qo["exit"]
                cursor = qo["exit"] or qo["enter"]
            pv = find_after(port_id, cursor)
            if pv:
                c["chan_may_in"], c["chan_may_out"] = pv["enter"], pv["exit"]
                cursor = pv["exit"] or pv["enter"]

            # Return leg — only after the port turnaround
            if pv and pv["exit"]:
                after_port = pv["exit"]
                lb = next((v for v in window
                           if v["anchor_id"] == border_id and v["enter"] > after_port), None)
                if lb:
                    c["lalay_back_in"], c["lalay_back_out"] = lb["enter"], lb["exit"]
                close_at = lb["enter"] if lb else None
                qb = next((v for v in window
                           if v["anchor_id"] == ql49_id and v["enter"] > after_port
                           and (close_at is None or v["enter"] < close_at)), None)
                if qb:
                    c["ql49_back_in"], c["ql49_back_out"] = qb["enter"], qb["exit"]
                    c["backhaul_type"] = "ql49"
                if detour_id:
                    dv = next((v for v in window
                               if v["anchor_id"] == detour_id and v["enter"] > after_port
                               and (close_at is None or v["enter"] < close_at)), None)
                    if dv:
                        c["detour_in"], c["detour_out"] = dv["enter"], dv["exit"]
                        c["backhaul_type"] = "both" if c["backhaul_type"] else "detour"
            seqs.append(c)
    seqs.sort(key=lambda c: c["cycle_date"])
    return seqs

# ── Status rows ──────────────────────────────────────────────────────────────
def reconcile_status(plate, haul, last, dispatch_plan, load_actual):
    if haul == "Fronthaul":
        return {"code": "fronthaul", "label": "\u2014", "detail": "fronthaul (ignored)"}
    if haul != "Backhaul":
        return {"code": "na", "label": "\u2014", "detail": ""}
    key = norm_plate_strict(plate)
    port_in = last.get("chan_may_in") if last else None
    if key and load_actual:
        mine = sorted([r for r in load_actual if r["key"] == key and r.get("load_in")],
                      key=lambda r: r["load_in"])
        fresh = [r for r in mine if (not port_in or r["load_in"] > port_in)]
        if fresh:
            rec = fresh[-1]
            net = f" \u00b7 {int(rec['net']):,} kg" if rec.get("net") else ""
            tk = f" \u00b7 {rec['ticket']}" if rec.get("ticket") else ""
            return {"code": "reloaded", "label": "Reloaded \u2713",
                    "detail": f"weighed {fmt(rec['load_in'])}{net}{tk}"}
    if key and dispatch_plan:
        hit = next((p for p in dispatch_plan if p["key"] == key), None)
        if hit:
            d = "load " + fmt(hit["load_start"]) if hit.get("load_start") else "on plan"
            return {"code": "planned", "label": "Planned", "detail": d}
    return {"code": "unassigned", "label": "Unassigned",
            "detail": "returning empty \u00b7 no next job"}

def fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""

def build_status_rows(plates, last_pings, sequences, routes, anchors, roles,
                      dispatch_plan=None, load_actual=None, deactivated=None):
    """
    Master status builder.
      plates:     list of plate strings
      last_pings: {plate: {lat, lng, dt, speed, status}}
      routes:     {leg_key: {points: [[lat,lng]...], speed}}
      anchors:    [{id, polygon, ...}]  (for gate centroids)
      roles:      {role_id: anchor_id}
    Returns list of row dicts.
    """
    deactivated = deactivated or set()
    dispatch_plan = dispatch_plan or []
    load_actual = load_actual or []
    anchor_by_id = {a["id"]: a for a in anchors}
    role_polys = {r: anchor_by_id[aid]["polygon"]
                  for r, aid in roles.items()
                  if aid in anchor_by_id}

    def leg_pts(k):
        r = routes.get(k)
        return r["points"] if r and r.get("points") else None

    def leg_speed(k, default):
        r = routes.get(k)
        return r["speed"] if r and r.get("speed", 0) > 0 else default

    rows = []
    for plate in sorted(plates):
        if norm_plate(plate) in deactivated:
            continue
        lp = last_pings.get(plate)
        seqs = sorted([c for c in sequences if norm_plate(c["plate"]) == norm_plate(plate)],
                      key=lambda c: c["cycle_date"])
        last = seqs[-1] if seqs else None

        haul, direction = "\u2014", ""
        if last:
            reached_port = bool(last.get("chan_may_in"))
            if reached_port and not last.get("xppl_r"):
                haul, direction = "Backhaul", "Port \u2192 Border \u2192 Mine"
            elif not reached_port:
                haul, direction = "Fronthaul", "Mine \u2192 Border \u2192 Port"
            else:
                haul = "Completed"

        rem_km, eta, eta_c, next_anchor = None, None, None, "\u2014"

        if haul == "Backhaul" and lp:
            north = remaining_and_snap(leg_pts("port_mine"), lp["lat"], lp["lng"]) \
                if leg_pts("port_mine") else None
            ql = remaining_and_snap(leg_pts("port_mine_ql49"), lp["lat"], lp["lng"]) \
                if leg_pts("port_mine_ql49") else None
            if last.get("backhaul_type") == "ql49" and ql:
                leg_key = "port_mine_ql49"
            elif ql and not north:
                leg_key = "port_mine_ql49"
            elif north and not ql:
                leg_key = "port_mine"
            elif ql and north:
                leg_key = "port_mine_ql49" if ql["snap_km"] < north["snap_km"] else "port_mine"
            else:
                leg_key = "port_mine"
            pts = leg_pts(leg_key)
            next_anchor = "Mine"
            if pts:
                rem = remaining_km_along_route(pts, lp["lat"], lp["lng"])
                if rem is not None:
                    rem_km = rem
                    spd = leg_speed(leg_key, 40)
                    eta = lp["dt"] + timedelta(hours=rem / spd)
                    eta_c = constraint_aware_eta(lp["dt"], pts, lp["lat"], lp["lng"],
                                                 spd, "Backhaul", last.get("backhaul_type"),
                                                 role_polys)

        if haul == "Fronthaul" and lp:
            best = None
            for k in FRONTHAUL_LEGS:
                pts = leg_pts(k)
                if not pts:
                    continue
                rs = remaining_and_snap(pts, lp["lat"], lp["lng"])
                if rs and (best is None or rs["snap_km"] < best["snap_km"]):
                    best = {"key": k, **rs}
            if best:
                spd = leg_speed(best["key"], 15)
                rem_to_port = best["rem"]
                idx = FRONTHAUL_LEGS.index(best["key"])
                for k2 in FRONTHAUL_LEGS[idx + 1:]:
                    pts2 = leg_pts(k2)
                    if pts2 and len(pts2) > 1:
                        for j in range(1, len(pts2)):
                            rem_to_port += haversine_km(pts2[j-1][0], pts2[j-1][1],
                                                        pts2[j][0], pts2[j][1])
                rem_km = rem_to_port
                eta = lp["dt"] + timedelta(hours=rem_to_port / spd)
                eta_c = constraint_aware_eta(lp["dt"], leg_pts(best["key"]),
                                             lp["lat"], lp["lng"], spd,
                                             "Fronthaul", None, role_polys)
                next_anchor = "Port"

        rec = reconcile_status(plate, haul, last, dispatch_plan, load_actual)

        rows.append({
            "plate": plate,
            "haul": haul,
            "direction": direction,
            "next": next_anchor,
            "rem_km": round(rem_km, 1) if rem_km is not None else None,
            "eta_raw": fmt(eta) if eta else "",
            "eta_criteria": fmt(eta_c) if eta_c else "",
            "last_seen": fmt(lp["dt"]) if lp else "",
            "status": rec["label"],
            "status_code": rec["code"],
            "status_detail": rec["detail"],
        })
    return rows
