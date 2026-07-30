"""
WI LA-NT-001 rules as data.

Encodes the non-negotiable route windows from Section 4 of the Work Instruction
and the return-route rule from Section 5.3, so that "did this truck make the
gate?" is evaluated by the program instead of read off a timestamp by eye.

Pure functions, no database, no Flask — safe to import anywhere and easy to test.
Times are local operating time (UTC+7); the plan chain is already local.
"""

# ── Section 4: route windows ────────────────────────────────────────────────
# entry_only: the window governs the moment of entry; exit is unrestricted.
# stage: the key on a plan row this window is checked against.
WINDOWS = [
    {"key": "border_loaded", "stage": "borderArrive",
     "label": "Lalay border, loaded (Mine to VN)", "start": "15:00", "end": "19:00",
     "entry_only": True, "binding": True, "note": "Once daily, hard gate"},
    {"key": "ql49_in", "stage": "portArrive",
     "label": "QL49 inbound loaded", "start": "19:00", "end": "24:00",
     "entry_only": True, "binding": False, "note": "Entry window only; exit unrestricted"},
    {"key": "port_unload", "stage": "depPort",
     "label": "Port unload", "start": "07:00", "end": "17:00",
     "entry_only": False, "binding": False, "note": "Standard time only"},
    {"key": "ql49_out", "stage": "borderBack",
     "label": "QL49 outbound empty", "start": "00:00", "end": "05:00",
     "entry_only": True, "binding": False, "note": "Entry window only; exit unrestricted"},
    {"key": "border_empty", "stage": "mineReturn",
     "label": "Lalay border, empty backhaul", "start": "07:00", "end": "19:00",
     "entry_only": True, "binding": False, "note": ""},
]

WINDOW_BY_KEY = {w["key"]: w for w in WINDOWS}

# The gate everything else is planned backwards from (Section 4.1).
BINDING_GATE = "border_loaded"

# ── Section 5.3: return route ───────────────────────────────────────────────
ROUTES = [
    {"key": "hue", "label": "Hue town", "cycle_hours": 48, "default": True,
     "note": "Default. No time-restricted leg on the return."},
    {"key": "ql49", "label": "QL49", "cycle_hours": 72, "default": False,
     "note": "Only where the truck still reaches the mine in time for the next gate."},
]
DEFAULT_ROUTE = "hue"
ROUTE_KEYS = [r["key"] for r in ROUTES]


def _mins(hhmm):
    """'15:00' -> 900.  '24:00' -> 1440 (end of day)."""
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)


def _tod_mins(dt):
    return dt.hour * 60 + dt.minute


def in_window(window_key, dt):
    """True/False if dt falls inside the window; None when dt is missing.

    Windows that wrap midnight (start > end) are handled, though none currently
    do — 24:00 is represented as end-of-day rather than a wrap.
    """
    if dt is None:
        return None
    w = WINDOW_BY_KEY.get(window_key)
    if not w:
        return None
    t = _tod_mins(dt)
    s, e = _mins(w["start"]), _mins(w["end"])
    if s <= e:
        return s <= t <= e
    return t >= s or t <= e   # wraps midnight


def check_row(row_times):
    """Evaluate one plan row against every window.

    row_times: {stage_key: datetime|None}
    Returns {window_key: {"stage","label","binding","ok","time"}} — ok is
    True / False / None (no time recorded, so nothing to judge).
    """
    out = {}
    for w in WINDOWS:
        dt = (row_times or {}).get(w["stage"])
        out[w["key"]] = {
            "stage": w["stage"],
            "label": w["label"],
            "binding": w["binding"],
            "window": w["start"] + "-" + w["end"],
            "ok": in_window(w["key"], dt),
            "time": dt.strftime("%Y-%m-%d %H:%M") if dt else None,
        }
    return out


def gate_ok(row_times):
    """Shorthand for the binding gate only (Section 4 — the one that matters)."""
    return in_window(BINDING_GATE, (row_times or {}).get(WINDOW_BY_KEY[BINDING_GATE]["stage"]))


def norm_plate(p):
    return "".join(ch for ch in str(p or "").upper() if ch.isalnum())
