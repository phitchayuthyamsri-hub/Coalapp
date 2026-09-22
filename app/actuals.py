# -*- coding: utf-8 -*-
"""Actual times, stamped once (22/09/2026).

What the GPS has already told us is written down and read back, rather than
worked out again from every ping each time a page opens:

  ActualStamp   the Monitor's actual cells - per run day, truck and event
  MineArrival   every time a truck entered the mine (the Managers page)
  AnchorSeen    which Locations the GPS has ever seen a truck inside

`stamp_recent()` runs after every GPS pull. It fills only what is blank. A
stamp once written is permanent: nothing here updates or deletes one.

The matching is the Monitor's own (`_match_cycle`, mine-first), so a stamp is
exactly the time the Monitor would have shown. Two rules keep "permanent"
honest:

  * an EXIT is written only once the truck has left. While it is still inside,
    the last ping inside is where the visit has got to, not where it ends;
  * the run home is walked from the last stop's exit (the port, or A Ngo),
    so nothing on it is written until the truck has left there.
"""
from datetime import datetime, timedelta

from .models import db, ActualStamp, MineArrival, AnchorSeen
from . import engine


def _events():
    """Every (leg, role, edge) the Monitor table or its shift checks read."""
    from .shift_routes import LOC_FH, LOC_BH, CHECK_EVENTS
    ev = []
    for spec, leg in ((LOC_FH, "fh"), (LOC_BH, "bh")):
        for _k, _l, _f, role, edge in spec:
            if role and (leg, role, edge) not in ev:
                ev.append((leg, role, edge))
    for leg, role, edge in CHECK_EVENTS.values():
        if (leg, role, edge) not in ev:
            ev.append((leg, role, edge))
    return ev


def stamp_days(days, visits, roles):
    """Stamp the blanks for these run days from these visits.

    Every truck the GPS saw, not only today's fleet: a plan issued last week
    names trucks that have since left the fleet, and the Monitor still shows
    that day.

    `visits` must hold every visit entered from the earliest day's start on.
    Returns how many stamps were written."""
    from .shift_routes import (_day_bounds, _match_route, _applies, _route_paths,
                               DEFAULT_PATH, CYCLE_SPAN)
    events = _events()
    # Each truck is walked along its own route (22/09/2026): Mine : A Ngo ends
    # at A Ngo the way the corridor ends at the port. A stamp already written
    # stays as it is if the truck later changes route.
    paths = _route_paths()
    by_plate = {}
    for v in visits:
        by_plate.setdefault(engine.norm_plate(v["plate"]), []).append(v)
    have = {}
    for s in ActualStamp.query.filter(ActualStamp.day.in_(list(days))).all():
        have[(s.day, s.key, s.leg, s.role, s.edge)] = True
    wrote = 0
    for day in days:
        lo, _hi = _day_bounds(day)
        for key in sorted(by_plate):
            vs = [v for v in by_plate.get(key, [])
                  if lo <= v["enter"] <= lo + CYCLE_SPAN]
            if not vs:
                continue
            path = paths.get(key, DEFAULT_PATH)
            matched = _match_route(vs, roles, path)
            end = matched.get(("fh", path[-1]))
            home_ready = end is not None and not end.get("open")
            for leg, role, edge in events:
                if (day, key, leg, role, edge) in have:
                    continue               # already said - permanent
                if not _applies(leg, role, edge, path):
                    continue               # not a place on this truck's route
                v = matched.get((leg, role))
                if v is None:
                    continue
                if leg == "bh" and not home_ready:
                    continue               # the run home starts at the last stop's exit
                if edge == "exit" and v.get("open"):
                    continue               # still inside: no exit yet
                at = v.get(edge) or v.get("enter")
                if at is None:
                    continue
                db.session.add(ActualStamp(day=day, key=key, leg=leg, role=role,
                                           edge=edge, at=at))
                have[(day, key, leg, role, edge)] = True
                wrote += 1
    return wrote


def record_arrivals(visits, roles):
    """Mine entries and seen Locations, from these visits. Blanks only."""
    mine_id = roles.get("xppl")
    got = 0
    if mine_id is not None:
        ents = {(engine.norm_plate(v["plate"]), v["enter"]) for v in visits
                if v.get("anchor_id") == mine_id and v.get("enter")}
        if ents:
            earliest = min(e for _k, e in ents)
            have = {(m.key, m.at) for m in
                    MineArrival.query.filter(MineArrival.at >= earliest).all()}
            for k, e in sorted(ents - have):
                db.session.add(MineArrival(key=k, at=e))
                got += 1
    seen = {a.anchor_id for a in AnchorSeen.query.all()}
    first = {}
    for v in visits:
        a = v.get("anchor_id")
        if a is not None and a not in seen:
            if a not in first or v["enter"] < first[a]:
                first[a] = v["enter"]
    for a, e in first.items():
        db.session.add(AnchorSeen(anchor_id=a, first_at=e))
    return got


def stamp_recent(now=None, back_days=5):
    """After a GPS pull: every run day whose three-day window is still open,
    plus a little behind it for pings that arrive late."""
    from .shift_routes import _visits_and_roles, _day_bounds, LOCAL_OFFSET
    now = now or (datetime.utcnow() + LOCAL_OFFSET)
    days = [(now - timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(back_days, -1, -1)]
    since = _day_bounds(days[0])[0]
    visits, roles = _visits_and_roles(since=since)
    visits = [v for v in visits if v["enter"] >= since]
    n = stamp_days(days, visits, roles)
    m = record_arrivals(visits, roles)
    db.session.commit()
    return {"days": days, "stamps": n, "mine_arrivals": m}


def backfill(first_day):
    """Once, at deploy: every run day from `first_day` to today, from the whole
    history."""
    from .shift_routes import _visits_and_roles, LOCAL_OFFSET
    now = datetime.utcnow() + LOCAL_OFFSET
    d = datetime.strptime(first_day, "%Y-%m-%d")
    days = []
    while d.date() <= now.date():
        days.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    visits, roles = _visits_and_roles()
    n = stamp_days(days, visits, roles)
    m = record_arrivals(visits, roles)
    db.session.commit()
    return {"days": len(days), "stamps": n, "mine_arrivals": m}


def stamps_for(day):
    """{(key, leg, role, edge): datetime} for one run day."""
    return {(s.key, s.leg, s.role, s.edge): s.at
            for s in ActualStamp.query.filter_by(day=day).all()}


def stamped_by(day):
    """{(key, leg, role, edge): username} for the stamps a person typed in."""
    return {(s.key, s.leg, s.role, s.edge): s.by
            for s in ActualStamp.query.filter_by(day=day).all() if s.by}


# The cell a person can type into that no zone ever stamps: unloading at the
# port is timed by the plan and marked by no geofence, so a typed time for it
# needs a key of its own.
MANUAL_ONLY = {("fh", "unload"): ("fh", "unload", "enter")}


def set_manual(day, key, leg, role, edge, at, who):
    """A person's time for one cell. Overwrites a GPS time or an earlier typed
    one; `at=None` clears a typed time (a GPS time is left alone). Returns
    the stamp, or None when cleared."""
    q = ActualStamp.query.filter_by(day=day, key=key, leg=leg, role=role, edge=edge)
    s = q.first()
    if at is None:
        if s is not None and s.by:
            db.session.delete(s)
        db.session.commit()
        return None
    if s is None:
        s = ActualStamp(day=day, key=key, leg=leg, role=role, edge=edge, at=at)
        db.session.add(s)
    s.at = at
    s.by = who
    s.stamped_at = datetime.utcnow()
    db.session.commit()
    return s


def seen_anchor_ids():
    return {a.anchor_id for a in AnchorSeen.query.all()}
