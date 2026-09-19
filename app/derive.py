"""Derive the visit and cycle layer once, instead of on every request.

Six analytics endpoints and the Monitor each rebuild every geofence visit and
every cycle from the whole ping table, per request. That work grows with
history and is repeated constantly; the answer for last August is recomputed
identically every time. This module computes the same two things and stores
them, so they are computed once.

Nothing in the app reads these tables yet. This is step 3 of the plan of
19/09/2026: build the layer, rebuild it from scratch, and prove it matches
what the live path computes. The switch-over is a later step.

    python rebuild_derived.py            # wipe and rebuild, then report
    python rebuild_derived.py --check    # compare stored against live, no write
"""

from datetime import datetime, timedelta

from . import engine, geofence
from .models import db, GpsPing, Truck, Visit, Cycle

# How long after its last ping a piece of work is taken as settled. One full
# mine-to-mine cycle is about 68 hours, so 72 clears a whole run with a margin.
# The right number depends on how far behind the providers backfill, which
# nobody has measured yet - see the plan's open questions.
SETTLE_HOURS = 72

CYCLE_FIELDS = (
    "xppl_in", "xppl_out", "loading_in", "loading_out",
    "lalay_out_in", "lalay_out_out", "ql49_out_in", "ql49_out_out",
    "chan_may_in", "chan_may_out", "ql49_back_in", "ql49_back_out",
    "detour_in", "detour_out", "lalay_back_in", "lalay_back_out",
    "xppl_r", "backhaul_type",
)


def compute_live():
    """Visits and cycles the way every page computes them today.

    Deliberately the same calls in the same order as api._engine_state, so a
    difference between this and the stored rows is a real difference and not
    two ways of asking.
    """
    anchors = geofence.for_engine()
    roles = geofence.roles()
    pings = [{"plate": p.plate, "dt": p.dt, "lat": p.lat, "lng": p.lng,
              "speed": p.speed, "status": p.status}
             for p in GpsPing.query.order_by(GpsPing.dt).all()]
    deactivated = {engine.norm_plate(t.plate) for t in
                   Truck.query.filter_by(status="deactivated").all()}
    visits = engine.build_visits(pings, anchors, deactivated)
    seqs = engine.recompute_sequences(visits, roles)
    return visits, seqs


def _settled_before(now=None):
    return (now or datetime.utcnow()) - timedelta(hours=SETTLE_HOURS)


def rebuild(now=None):
    """Drop both tables and derive them again from every ping.

    The escape hatch: whenever the stored layer and the pings disagree, this
    is what puts them back in step. It is also how the layer is first filled.
    """
    horizon = _settled_before(now)
    visits, seqs = compute_live()

    Visit.query.delete()
    Cycle.query.delete()
    db.session.flush()

    for v in visits:
        # Settled means: left the zone, and old enough that a late ping can no
        # longer change it. An open visit is never frozen - the truck is still
        # inside and its exit has not happened yet.
        last_seen = v.get("exit") or v["enter"]
        frozen = (not v.get("open")) and last_seen < horizon
        db.session.add(Visit(
            plate=v["plate"], anchor_id=v["anchor_id"],
            anchor_name=v.get("anchor_name") or "",
            visit_num=v.get("visit_num") or 0,
            enter=v["enter"], exit=v.get("exit"),
            open=bool(v.get("open")), ping_count=v.get("ping_count") or 0,
            frozen_at=(now or datetime.utcnow()) if frozen else None))

    for c in seqs:
        # A cycle closes when the truck reaches the mine again (xppl_r). Until
        # then the road is still writing it, however old its start is.
        closed = c.get("xppl_r") is not None
        frozen = closed and c["xppl_r"] < horizon
        row = Cycle(plate=c["plate"], cycle_date=c["cycle_date"],
                    frozen_at=(now or datetime.utcnow()) if frozen else None)
        for f in CYCLE_FIELDS:
            setattr(row, f, c.get(f))
        db.session.add(row)

    db.session.commit()
    return {"visits": len(visits), "cycles": len(seqs),
            "visits_frozen": Visit.query.filter(Visit.frozen_at.isnot(None)).count(),
            "cycles_frozen": Cycle.query.filter(Cycle.frozen_at.isnot(None)).count()}


def check():
    """Compare what is stored against what the live path computes now.

    Reports counts and the first few differences rather than just a verdict:
    if the two disagree, the useful thing is which row and which field.
    """
    visits, seqs = compute_live()
    live_v = {(v["plate"], v["anchor_id"], v["enter"]): v for v in visits}
    live_c = {(c["plate"], c["cycle_date"]): c for c in seqs}

    stored_v = {(r.plate, r.anchor_id, r.enter): r for r in Visit.query.all()}
    stored_c = {(r.plate, r.cycle_date): r for r in Cycle.query.all()}

    diffs = []
    for k in set(live_v) | set(stored_v):
        lv, sv = live_v.get(k), stored_v.get(k)
        if lv is None:
            diffs.append(("visit only stored", k)); continue
        if sv is None:
            diffs.append(("visit only live", k)); continue
        if (lv.get("exit") != sv.exit or bool(lv.get("open")) != bool(sv.open)
                or (lv.get("ping_count") or 0) != (sv.ping_count or 0)):
            diffs.append(("visit fields differ", k))

    for k in set(live_c) | set(stored_c):
        lc, sc = live_c.get(k), stored_c.get(k)
        if lc is None:
            diffs.append(("cycle only stored", k)); continue
        if sc is None:
            diffs.append(("cycle only live", k)); continue
        for f in CYCLE_FIELDS:
            if lc.get(f) != getattr(sc, f):
                diffs.append(("cycle %s differs" % f, k))
                break

    return {"live_visits": len(live_v), "stored_visits": len(stored_v),
            "live_cycles": len(live_c), "stored_cycles": len(stored_c),
            "differences": len(diffs), "first": diffs[:10]}
