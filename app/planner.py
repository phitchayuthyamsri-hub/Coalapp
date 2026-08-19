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
from .models import PlanSetting, RouteLeg

LOCAL = timedelta(hours=7)          # everything below is local time, UTC+7


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
        km = 0.0
        if r.points:
            km = sum(engine.haversine_km(r.points[i][0], r.points[i][1],
                                         r.points[i + 1][0], r.points[i + 1][1])
                     for i in range(len(r.points) - 1))
        legs[r.leg_key] = {"km": km, "speed": r.speed or 30.0,
                           "hours": (km / r.speed) if r.speed else 0.0}
    return {
        "load_h": hours("load_hours", 1.0),
        "turn_gap_h": hours("turn_gap_hours", 0.0),
        "unload_h": hours("unload_hours", 0.5),
        "clear_h": hours("clearance_hours", 3.0),
        "mine_bays": count("mine_bays", 2),
        "port_bays": count("port_bays", 1),
        "mine_247": str(s.get("mine_247", "yes")).lower().startswith("y"),
        "border_open": hhmm("border_open", "15:00"),
        "border_close": hhmm("border_close", "19:00"),
        "ql49_in_open": hhmm("ql49_in_open", "19:00"),
        "ql49_in_close": hhmm("ql49_in_close", "24:00"),
        "port_open": hhmm("port_open", "07:00"),
        "port_close": hhmm("port_close", "17:00"),
        "ql49_out_open": hhmm("ql49_out_open", "00:00"),
        "ql49_out_close": hhmm("ql49_out_close", "05:00"),
        "cutoff": hhmm("backhaul_cutoff", "14:00"),
        "legs": legs,
    }


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
