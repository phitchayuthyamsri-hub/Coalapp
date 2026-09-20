# -*- coding: utf-8 -*-
"""The one place geofences are read for the engine and written by anyone.

Two decisions live here, both from 18/09/2026:

  A change never rewrites history. Every shape a zone has had is a dated
  version, and a ping is judged against the version in force when it was
  captured. Move a boundary at 10:00 and the 09:55 ping is still judged by
  the old one. Retiring a zone is the same kind of change: it stops matching
  from that moment, never before.

  The server is the only store. The tool's Parameter page used to keep its
  own copy in the browser and the Monitor read this table, so an edit on one
  never reached the other. Now every reader - Monitor, the maps, the GPS
  poller, the tool - comes through here, and the Parameter page writes back
  through the API in api.py, which calls the functions below.
"""
from datetime import datetime, timedelta

from .models import db, Anchor, AnchorVersion

ROLE_KEYS = ("xppl", "loading", "border", "ql49", "ql49b", "ql49p", "port", "detour")

# GpsPing.dt is stored on the local clock (UTC+7). A version's valid_from is
# only ever compared with a ping's dt, so it has to be on the same clock, or
# an edit at 10:00 local would apply to pings from 03:00 - seven hours of
# history quietly rejudged.
_LOCAL = timedelta(hours=7)


def ping_clock_now():
    return (datetime.utcnow() + _LOCAL).replace(microsecond=0)


# -- reading ------------------------------------------------------------------
def _versions_by_anchor():
    out = {}
    for v in AnchorVersion.query.order_by(AnchorVersion.anchor_id).all():
        out.setdefault(v.anchor_id, []).append(
            {"valid_from": v.valid_from, "polygon": v.polygon,
             "min_dwell_min": v.min_dwell_min if v.min_dwell_min is not None else 5})
    # NULL valid_from means "since the beginning" and must sort first. SQLite
    # happens to put NULLs first; do not rely on any database for it.
    for vs in out.values():
        vs.sort(key=lambda v: (v["valid_from"] is not None,
                               v["valid_from"] or datetime.min))
    return out


def for_engine():
    """Every zone, retired ones included, in the shape engine.build_visits
    reads - with its versions, so the engine can pick the right one per ping."""
    vers = _versions_by_anchor()
    return [{"id": a.id, "name": a.name, "polygon": a.polygon,
             "min_dwell_min": a.min_dwell_min if a.min_dwell_min is not None else 5,
             "versions": vers.get(a.id) or [],
             "retired_at": a.retired_at}
            for a in Anchor.query.order_by(Anchor.id).all()]


def roles():
    """{role: anchor_id} for the zones still in service."""
    return {a.role: a.id for a in Anchor.query.all()
            if a.role and a.retired_at is None}


def current_polygons():
    """The shapes in force right now - what a map draws and what the GPS
    poller uses to decide how often to ask a truck."""
    return [a.polygon for a in Anchor.query.all()
            if a.retired_at is None and a.polygon and len(a.polygon) >= 3]


def as_api(a):
    return {"id": a.id, "name": a.name, "color": a.color or "#34c759",
            "category": a.category or "", "caption": a.caption or "",
            "role": a.role or "", "polygon": a.polygon,
            "min_dwell_min": a.min_dwell_min if a.min_dwell_min is not None else 5,
            "loc_type": a.loc_type or "",
            "window_open": a.window_open or "",
            "window_close": a.window_close or "",
            "loading_bays": a.loading_bays,
            "loading_time_min": a.loading_time_min,
            "retired_at": a.retired_at.strftime("%Y-%m-%d %H:%M") if a.retired_at else None}


# -- the place's working conditions (20/09/2026) ------------------------------
# Labels, not judgements: like name and colour they change in place and write
# no version, because none of them can change how a past ping was judged.
LOC_TYPES = ("", "load", "unload", "load_unload", "border", "highway")


def _hhmm(v):
    """A clock time as "HH:MM", or "" for no window.

    Refused rather than quietly blanked when it is neither: a window someone
    typed and the server silently dropped is worse than an error, because the
    page would go on showing it until the next reload.
    """
    s = str(v or "").strip()
    if not s:
        return ""
    parts = s.split(":")
    if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
        raise ValueError("a window time reads HH:MM, or is blank for all day")
    h, m = int(parts[0]), int(parts[1])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("a window time reads HH:MM, or is blank for all day")
    return "%02d:%02d" % (h, m)


def _whole(v, what):
    """A whole number at or above zero, or None for "not recorded"."""
    if v is None or str(v).strip() == "":
        return None
    try:
        n = int(float(str(v).strip()))
    except (TypeError, ValueError):
        raise ValueError("%s is a whole number" % what)
    if n < 0:
        raise ValueError("%s cannot be negative" % what)
    return n


def apply_conditions(a, d):
    """Set whatever conditions the caller sent, leaving the rest alone.

    The open and close times are NOT checked against each other: a window that
    runs 22:00 to 06:00 is a night shift, not a mistake.
    """
    if "loc_type" in d:
        t = (d.get("loc_type") or "").strip().lower()
        if t not in LOC_TYPES:
            raise ValueError("unknown location type %r" % t)
        a.loc_type = t
    if "window_open" in d:
        a.window_open = _hhmm(d.get("window_open"))
    if "window_close" in d:
        a.window_close = _hhmm(d.get("window_close"))
    if "loading_bays" in d:
        a.loading_bays = _whole(d.get("loading_bays"), "loading bays")
    if "loading_time_min" in d:
        a.loading_time_min = _whole(d.get("loading_time_min"), "loading time")


# -- writing ------------------------------------------------------------------
def _valid_polygon(poly):
    return (isinstance(poly, list) and len(poly) >= 3
            and all(isinstance(p, (list, tuple)) and len(p) == 2 for p in poly))


# About a centimetre. Leaflet re-serialises a polygon on every edit and the
# last digits drift; a zone nobody moved must compare equal to itself, and a
# rounding comparison does not promise that - a nanometre can flip a digit.
_SAME = 1e-7


def _same_shape(a, b):
    try:
        if len(a) != len(b):
            return False
        return all(len(p) == len(q) == 2
                   and abs(float(p[0]) - float(q[0])) <= _SAME
                   and abs(float(p[1]) - float(q[1])) <= _SAME
                   for p, q in zip(a, b))
    except (TypeError, ValueError):
        return False


def ensure_versions():
    """Every zone gets a first version - "since the beginning" - if it has
    none. Runs at boot; idempotent. This is what makes history stay put on
    the day versioning arrives: the shape already in the table IS the history."""
    have = {row[0] for row in db.session.query(AnchorVersion.anchor_id).distinct()}
    added = 0
    for a in Anchor.query.all():
        if a.id in have:
            continue
        db.session.add(AnchorVersion(anchor_id=a.id, polygon=a.polygon,
                                     min_dwell_min=a.min_dwell_min, valid_from=None,
                                     set_by="backfill"))
        added += 1
    if added:
        db.session.commit()
    return added


def create(d, who):
    """A new zone. Its first version takes effect now - pings before this
    moment never saw it, which is the truth."""
    poly = d.get("polygon")
    if not _valid_polygon(poly):
        raise ValueError("a polygon needs at least three [lat, lng] points")
    name = (d.get("name") or "").strip()
    if not name:
        raise ValueError("a zone needs a name")
    now = ping_clock_now()
    a = Anchor(name=name[:120], color=(d.get("color") or "#34c759")[:20],
               category=(d.get("category") or "")[:40],
               caption=(d.get("caption") or "")[:60],
               polygon=poly, min_dwell_min=int(d.get("min_dwell_min") or 5),
               role=(d.get("role") or "")[:20])
    apply_conditions(a, d)
    db.session.add(a)
    db.session.flush()
    db.session.add(AnchorVersion(anchor_id=a.id, polygon=poly,
                                 min_dwell_min=a.min_dwell_min, valid_from=now,
                                 set_by=(who or "")[:80]))
    db.session.commit()
    return a


def update(a, d, who):
    """Apply what the caller sent. Name, colour, category, caption, role and
    the place's working conditions change in place - they are labels, not
    judgements. A changed polygon or
    dwell is a new VERSION from now, and an unchanged one is not: pressing
    Apply on a zone you did not move must not manufacture history.

    -> True if a new version was written."""
    if "name" in d and (d["name"] or "").strip():
        a.name = d["name"].strip()[:120]
    if "color" in d and d["color"]:
        a.color = str(d["color"])[:20]
    if "category" in d:
        a.category = (d.get("category") or "")[:40]
    if "caption" in d:
        a.caption = (d.get("caption") or "")[:60]
    if "role" in d:
        a.role = (d.get("role") or "")[:20]
    apply_conditions(a, d)

    new_poly = d.get("polygon") if "polygon" in d else None
    if new_poly is not None and not _valid_polygon(new_poly):
        raise ValueError("a polygon needs at least three [lat, lng] points")
    new_dwell = None
    if "min_dwell_min" in d and d["min_dwell_min"] is not None:
        new_dwell = int(d["min_dwell_min"])

    cur_dwell = a.min_dwell_min if a.min_dwell_min is not None else 5
    shape_changed = new_poly is not None and not _same_shape(new_poly, a.polygon)
    dwell_changed = new_dwell is not None and new_dwell != cur_dwell
    versioned = False
    if shape_changed or dwell_changed:
        # A zone that somehow has no version yet gets its ORIGINAL shape
        # recorded as "since the beginning" before the new one is written.
        # Otherwise the first edit would be the zone's earliest known shape
        # and every ping before it would be judged as outside a zone that
        # did not exist - history lost by a boot-order accident.
        if not AnchorVersion.query.filter_by(anchor_id=a.id).first():
            db.session.add(AnchorVersion(anchor_id=a.id, polygon=a.polygon,
                                         min_dwell_min=cur_dwell, valid_from=None,
                                         set_by="backfill"))
        if shape_changed:
            a.polygon = new_poly
        if dwell_changed:
            a.min_dwell_min = new_dwell
        db.session.add(AnchorVersion(anchor_id=a.id, polygon=a.polygon,
                                     min_dwell_min=a.min_dwell_min,
                                     valid_from=ping_clock_now(),
                                     set_by=(who or "")[:80]))
        versioned = True
    db.session.commit()
    return versioned


def retire(a, who):
    """Stops matching from now. Kept, not deleted: its visits are history."""
    if a.retired_at is None:
        a.retired_at = ping_clock_now()
        a.role = ""
        db.session.commit()
    return a


def set_roles(mapping):
    """{role: anchor_id}. One zone per role; a role not in the mapping is
    cleared. Unknown role names and retired zones are ignored."""
    want = {}
    for k, v in (mapping or {}).items():
        if k in ROLE_KEYS and v:
            try:
                want[k] = int(v)
            except (TypeError, ValueError):
                pass
    for a in Anchor.query.all():
        if a.retired_at is not None:
            continue
        mine = [k for k, v in want.items() if v == a.id]
        a.role = mine[0] if mine else ""
    db.session.commit()
    return roles()
