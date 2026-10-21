# -*- coding: utf-8 -*-
"""Which trucks a login may see on the fleet (21/10/2026).

A subcontractor company sees its own fleet: the trucks the fleet register
gives to it (Truck.subcontractor_id), the trucks it has committed, and any
truck it has put on one of its own readiness sheets - so a truck a colleague
from the same company uploaded is there too. Everyone else - the admin and
the operations desks - sees the whole fleet.

All 54 trucks were Bac Nam's when this arrived, so Bac Nam sees every one of
them; Hoanh Son, PTS and Bao Binh see what is theirs.
"""
from . import engine
from .models import db, Truck, FleetCommitment, DailyList, DailyListRow


def visible_keys(user):
    """None for "every truck", else the set of normalised plates."""
    role = (getattr(user, "role", "") or "").lower()
    if getattr(user, "is_admin", False) or role != "subcontractor":
        return None
    sub = getattr(user, "subcontractor_id", None)
    if not sub:
        return set()
    keys = {engine.norm_plate(t.plate)
            for t in Truck.query.filter_by(subcontractor_id=sub).all()}
    keys |= {c.key for c in FleetCommitment.query.filter_by(subcontractor_id=sub).all()
             if not (c.released_on or "")}
    keys |= {r[0] for r in (db.session.query(DailyListRow.key)
                            .join(DailyList, DailyList.id == DailyListRow.list_id)
                            .filter(DailyList.subcontractor_id == sub).all()) if r[0]}
    return keys
