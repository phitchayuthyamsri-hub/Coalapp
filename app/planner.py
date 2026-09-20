# -*- coding: utf-8 -*-
"""Turn a readiness list into a dispatch plan.

Given when each truck reaches the mine, walk it round the loop: load, run to the
border, wait for the gate, QL49, port, unload, then Hue or the QL49 window by the
back-haul cut-off, and home. Every duration, gate and bay count is a PlanSetting
or a RouteLeg speed, so the operation can correct the model without a deploy.

Two things make this more than arithmetic:
  * gates - a truck that arrives early waits; that wait is the plan, not slack
  * bays  - the mine has 2 and the port 1, so trucks queue behind each other
"""
from datetime import datetime, timedelta

from . import engine
from .models import PlanSetting, RouteLeg, Anchor

LOCAL = timedelta(hours=7)          # everything below is local time, UTC+7


# ── where a figure comes from ───────────────────────────────────────────────
# The Location page describes each place: when it is open in each direction,
# how many bays it has, how long the work there takes. Those are the same
# facts the planning figures held, so from 20/09/2026 the Location is asked
# first and the figure is what answers when the Location is silent.
#
# Silent means blank, which means nobody has said - not "open all day" and not
# "no bays". Falling back rather than guessing is what keeps an unfilled
# Location from quietly changing a plan.
#
# Places are found by ROLE, not by name: a role is what the engine already
# uses to know which zone is the mine and which is the border, and renaming a
# zone must not detach its figures.
# The figures the Location page now answers for. Named once, here, so the
# screen that hides them and the planner that reads them cannot drift apart.
LOCATION_DERIVED = {
    "load_hours": "the loading area (or the mine) - Load/Unload time",
    "mine_bays": "the loading area (or the mine) - Load/Unload bay",
    "mine_247": "the mine - leaving both windows blank",
    "unload_hours": "the port - Load/Unload time",
    "port_bays": "the port - Load/Unload bay",
    "port_open": "the port - Window time, To port",
    "port_close": "the port - Window time, To port",
    "border_open": "the border - Window time, To port",
    "border_close": "the border - Window time, To port",
    "border_out_open": "the border - Window time, To mine",
    "border_out_close": "the border - Window time, To mine",
    "ql49_in_open": "QL49 - Window time, To port",
    "ql49_in_close": "QL49 - Window time, To port",
    "ql49_out_open": "QL49 - Window time, To mine",
    "ql49_out_close": "QL49 - Window time, To mine",
}


def _by_role():
    out = {}
    for a in Anchor.query.filter(Anchor.retired_at.is_(None)).all():
        if a.role:
            out[a.role] = a
    return out


def _win(a, direction):
    """A Location's window for one direction, or None if it has not said."""
    if a is None:
        return None
    o = getattr(a, "window_%s_open" % direction, "") or ""
    c = getattr(a, "window_%s_close" % direction, "") or ""
    if not o or not c:
        return None
    try:
        return (int(o.split(":")[0]), int(o.split(":")[1]),
                int(c.split(":")[0]), int(c.split(":")[1]))
    except (ValueError, IndexError):
        return None


# ── settings ────────────────────────────────────────────────────────────────
def load_config():
    s = {p.key: p.value for p in PlanSetting.query.all()}

    def hours(k, d):
        try:
            return float(s.get(k, d))
        except (TypeError, ValueError):
            return float(d)

    def count(k, d):
        try:
            return max(1, int(float(s.get(k, d))))
        except (TypeError, ValueError):
            return int(d)

    def hhmm(k, d):
        v = str(s.get(k, d) or d)
        try:
            h, m = v.split(":")
            return int(h), int(m)
        except ValueError:
            h, m = d.split(":")
            return int(h), int(m)

    legs = {}
    for r in RouteLeg.query.all():
        # The stored road distance wins. Falling back to the drawn line keeps
        # a hand-drawn leg working, but that line is thinned for the map, so
        # measuring it back is both slower and slightly short.
        km = float(r.road_km or 0.0)
        if not km and r.points:
            km = sum(engine.haversine_km(r.points[i][0], r.points[i][1],
                                         r.points[i + 1][0], r.points[i + 1][1])
                     for i in range(len(r.points) - 1))
        legs[r.leg_key] = {"km": km, "speed": r.speed or 30.0,
                           "hours": (km / r.speed) if r.speed else 0.0}
    # The Location page answers first; the figure answers when it is silent.
    z = _by_role()
    mine_work = z.get("loading") or z.get("xppl")    # loading area if drawn

    def mins(a, k, d):
        """A place's work time, in hours. The Location holds minutes."""
        v = getattr(a, "loading_time_min", None) if a is not None else None
        return (float(v) / 60.0) if v is not None else hours(k, d)

    def bays(a, k, d):
        v = getattr(a, "loading_bays", None) if a is not None else None
        return max(1, int(v)) if v else count(k, d)

    def window(a, direction, ko, kc, do, dc):
        w = _win(a, direction)
        return ((w[0], w[1]), (w[2], w[3])) if w else (hhmm(ko, do), hhmm(kc, dc))

    b_out = window(z.get("border"), "out", "border_open", "border_close", "15:00", "19:00")
    b_back = window(z.get("border"), "back", "border_out_open", "border_out_close", "07:00", "19:00")
    q_out = window(z.get("ql49"), "out", "ql49_in_open", "ql49_in_close", "19:00", "24:00")
    q_back = window(z.get("ql49"), "back", "ql49_out_open", "ql49_out_close", "00:00", "05:00")
    p_out = window(z.get("port"), "out", "port_open", "port_close", "07:00", "17:00")

    return {
        "load_h": mins(mine_work, "load_hours", 1.0),
        # Not a place's property: rest before turning again is the truck's.
        "turn_gap_h": hours("turn_gap_hours", 0.0),
        "unload_h": mins(z.get("port"), "unload_hours", 0.5),
        # Stays a figure: a Border Location has no Load/Unload time field
        # to hold it, so there is nowhere else for it to be said.
        "clear_h": hours("clearance_hours", 3.0),
        "mine_bays": bays(mine_work, "mine_bays", 2),
        "port_bays": bays(z.get("port"), "port_bays", 1),
        # A mine with no window in either direction is a mine that never shuts.
        "mine_247": (not _win(z.get("xppl"), "out") and not _win(z.get("xppl"), "back"))
                    if z.get("xppl") is not None
                    else str(s.get("mine_247", "yes")).lower().startswith("y"),
        "border_open": b_out[0],
        "border_close": b_out[1],
        "border_out_open": b_back[0],
        "border_out_close": b_back[1],
        "ql49_in_open": q_out[0],
        "ql49_in_close": q_out[1],
        "port_open": p_out[0],
        "port_close": p_out[1],
        "ql49_out_open": q_back[0],
        "ql49_out_close": q_back[1],
        # Which way home, by when unloading finished - a choice between routes,
        # so it stays a planning figure.
        "cutoff": hhmm("backhaul_cutoff", "14:00"),
        "legs": legs,
    }


def legs_between(cfg):
    """Every leg, indexed by the two stops it runs between.

    {(from_id, to_id): [ {via, km, speed, hours}, ... ]}

    A pair can hold more than one leg - two ways between the same stops is
    normal here, and the list keeps them in the order the operation entered
    them so "the first one" means something rather than whatever the database
    happened to return.
    """
    out = {}
    for r in RouteLeg.query.order_by(RouteLeg.id).all():
        if not r.from_anchor_id or not r.to_anchor_id:
            continue                       # a corridor-only leg, called by name
        km = float(r.road_km or 0.0)
        spd = float(r.speed or 0.0)
        out.setdefault((r.from_anchor_id, r.to_anchor_id), []).append({
            "leg_key": r.leg_key, "via": r.via or "", "km": km, "speed": spd,
            "hours": (km / spd) if spd else 0.0,
        })
    return out


def leg_for(index, a_id, b_id, via=None):
    """The leg between two stops, or None when nobody has measured it.

    None is the honest answer and the caller has to say so in the plan: a
    missing leg silently costing nothing is how a truck arrives before it
    left. `via` picks a named alternative; without one the first entered wins.
    """
    opts = index.get((a_id, b_id))
    if not opts:
        return None
    if via:
        want = str(via).strip().lower()
        for o in opts:
            if (o["via"] or "").strip().lower() == want:
                return o
    return opts[0]

# ── time helpers ────────────────────────────────────────────────────────────
def _at(day, hm):
    """hm as a time on `day`. 24:00 means midnight ending that day."""
    h, m = hm
    return day.replace(hour=0, minute=0, second=0, microsecond=0) \
        + timedelta(hours=h, minutes=m)


def next_window(t, open_hm, close_hm):
    """Move t forward to the next moment the window is open.

    Returns (start, waited_hours). A window whose close is at or before its open
    runs through midnight.
    """
    for day_shift in range(0, 3):
        day = t + timedelta(days=day_shift)
        o = _at(day, open_hm)
        c = _at(day, close_hm)
        if c <= o:                       # crosses midnight
            c += timedelta(days=1)
        if t < o:
            return o, (o - t).total_seconds() / 3600.0
        if o <= t < c:
            return t, 0.0
    return t, 0.0


class Bays(object):
    """A set of identical bays worked first-come-first-served."""

    def __init__(self, n):
        self.free = [None] * max(1, n)

    def take(self, arrive, dur_h, window=None):
        """Occupy the earliest free bay. Returns (start, end, waited_hours)."""
        start = arrive
        waited = 0.0
        if window:
            start, waited = next_window(start, window[0], window[1])
        # earliest bay that is free at or before we want to start
        idx = min(range(len(self.free)),
                  key=lambda i: self.free[i] or datetime.min)
        busy_until = self.free[idx]
        if busy_until and busy_until > start:
            waited += (busy_until - start).total_seconds() / 3600.0
            start = busy_until
            if window:                   # queueing may push us out of the window
                start, more = next_window(start, window[0], window[1])
                waited += more
        end = start + timedelta(hours=dur_h)
        self.free[idx] = end
        return start, end, waited


def _leg(cfg, key, default_h=0.0):
    return cfg["legs"].get(key, {}).get("hours", default_h)


# ── the plan ────────────────────────────────────────────────────────────────
def plan_trucks(arrivals, cfg=None):
    """arrivals: [(plate, datetime_at_mine_local)] -> one row per truck.

    Trucks are processed in arrival order, so the bay queues form the same way
    they would on the ground.
    """
    cfg = cfg or load_config()
    mine = Bays(cfg["mine_bays"])
    port = Bays(cfg["port_bays"])
    out = []

    for plate, arrive in sorted(arrivals, key=lambda x: x[1]):
        r = {"plate": plate, "arrive_mine": arrive, "waits": {}, "notes": []}

        mine_window = None if cfg["mine_247"] else (cfg["port_open"], cfg["port_close"])
        ls, le, w = mine.take(arrive, cfg["load_h"], mine_window)
        r["load_start"], r["load_end"] = ls, le
        r["waits"]["mine_queue"] = round(w, 2)

        depart = le
        r["depart_mine"] = depart
        r["arrive_border"] = depart + timedelta(hours=_leg(cfg, "mine_border"))

        cleared = r["arrive_border"] + timedelta(hours=cfg["clear_h"])
        cross, w = next_window(cleared, cfg["border_open"], cfg["border_close"])
        r["cross_border"] = cross
        r["waits"]["border_gate"] = round(w, 2)

        ql = cross + timedelta(hours=_leg(cfg, "border_ql49b"))
        ql_in, w = next_window(ql, cfg["ql49_in_open"], cfg["ql49_in_close"])
        r["ql49_in"] = ql_in
        r["waits"]["ql49_gate"] = round(w, 2)

        r["arrive_port"] = ql_in + timedelta(hours=_leg(cfg, "ql49b_ql49p")
                                             + _leg(cfg, "ql49p_port"))
        us, ue, w = port.take(r["arrive_port"], cfg["unload_h"],
                              (cfg["port_open"], cfg["port_close"]))
        r["unload_start"], r["unload_end"] = us, ue
        r["waits"]["port_queue"] = round(w, 2)

        # The back-haul rule: finished by the cut-off takes Hue and keeps the
        # 48-hour cycle; after it, the QL49 window costs a day.
        cutoff = _at(ue, cfg["cutoff"])
        if ue <= cutoff:
            r["route"] = "hue"
            r["depart_port"] = ue
            r["arrive_mine_back"] = ue + timedelta(hours=_leg(cfg, "port_mine"))
        else:
            r["route"] = "ql49"
            dep, w = next_window(ue, cfg["ql49_out_open"], cfg["ql49_out_close"])
            r["depart_port"] = dep
            r["waits"]["ql49_out_gate"] = round(w, 2)
            r["arrive_mine_back"] = dep + timedelta(hours=_leg(cfg, "port_mine_ql49"))

        r["cycle_hours"] = round(
            (r["arrive_mine_back"] - arrive).total_seconds() / 3600.0, 1)
        r["total_wait"] = round(sum(r["waits"].values()), 1)
        if r["cycle_hours"] > 60:
            r["notes"].append("cycle over 60 h")
        out.append(r)
    return out
