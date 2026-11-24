"""Fill the holes in captured GPS from each provider's route history (24/11/2026).

The minute pull asks every provider where each truck is NOW. A tracker out of
signal - at the mine, on the Laos side - keeps its positions and uploads them
when it is back in coverage; they go into the provider's route history, but
"where is it now" never returns them. So the mine visit is missing here and the
Daily page reads the truck as "did not come", while the provider's own trail
map shows it at the mine (20C21788 on 20/11: at the mine 01:10-12:36 in TCT's
history, nothing captured until 19:41). Against the weighbridge, 1-10/11, about
a third of real loads had no captured mine visit.

This finds holes of GAP_MIN or more in each truck's captured positions, asks the
truck's own provider for its route history over just those hours, and stores
what it returns through the normal ingest (idempotent, own provider only, glitch
fixes dropped). The mine visits are then recorded for the days it touched, and
the Daily page picks the rest up on its next sync. Nothing else is written.
"""
import time
from datetime import datetime, timedelta

from . import gps_ingest as gi
from .models import db, GpsGapFill, GpsPing, Truck

GAP_MIN = timedelta(minutes=90)     # a shorter silence is a parked truck, not a lost visit
EDGE = timedelta(minutes=1)         # history points this close to a captured one are the same fix
CHUNK = timedelta(hours=24)         # one history call covers at most a day
RETRY_AFTER = timedelta(hours=3)    # a hole the provider had nothing for is asked again...
RETRY_TIMES = 3                     # ...this many times...
RETRY_WINDOW = timedelta(hours=72)  # ...while it is this recent; then it is left alone
TRAILS = {"tct": gi._trail_tct, "tct2": gi._trail_tct, "binhanh": gi._trail_tct,
          "binhanh2": gi._trail_tct, "binhanh3": gi._trail_tct,
          "adsun": gi._trail_adsun, "adsun2": gi._trail_adsun, "viettel": gi._trail_viettel}


def _local_now():
    return datetime.utcnow() + gi._TZ_OFFSET


def trucks(since):
    """[(plate key, provider account key)] - every truck with a provider that has
    a route history, running now or still in the fleet at `since`.

    The fleet names the provider family (TCT, Binh Anh, Adsun); the account is
    the one its positions actually come from - 20C21788 is "TCT" on the fleet
    and reports through the second TCT account (api:tct2). Taken from the
    truck's latest stored position of that family; a truck that never sent one
    has no account to ask."""
    reg = gi.registered_providers()
    day = since.strftime("%Y-%m-%d")
    latest = {}
    for plate, src, at in (db.session.query(GpsPing.plate, GpsPing.source, db.func.max(GpsPing.dt))
                           .filter(GpsPing.dt >= since - timedelta(days=14))
                           .group_by(GpsPing.plate, GpsPing.source).all()):
        k = gi._norm_plate(plate)
        latest.setdefault(k, []).append((at, src or ""))
    out = []
    for t in Truck.query.all():
        k = gi._norm_plate(t.plate)
        fam = reg.get(k)
        if not fam:
            continue
        if (t.status or "") == "deactivated" and not ((t.eff_to or "") >= day):
            continue
        srcs = sorted((s for s in latest.get(k, []) if s[1].startswith("api:" + fam)), reverse=True)
        if not srcs:
            continue
        acct = srcs[0][1][4:]
        if acct in TRAILS:
            out.append((k, acct))
    return sorted(out)


def find_gaps(key_plate, source_key, since, until):
    """Holes in one truck's captured positions in [since, until], as
    (provider plate, gap_from, gap_to) - gap_from / gap_to are the captured
    positions either side (since / until at the ends), local time."""
    src = "api:" + source_key
    rows = (db.session.query(GpsPing.plate, GpsPing.dt)
            .filter(GpsPing.source == src, GpsPing.dt >= since - GAP_MIN, GpsPing.dt <= until)
            .filter(GpsPing.plate.in_(_spellings(key_plate, src)))
            .order_by(GpsPing.dt).all())
    plate = rows[-1][0] if rows else _provider_plate(key_plate)
    times = [r[1] for r in rows]
    edges = [since] + [t for t in times if t >= since] + [until]
    if times and times[0] < since:
        edges[0] = max(t for t in times if t < since)
    out = []
    for a, b in zip(edges, edges[1:]):
        if b - a >= GAP_MIN:
            out.append((plate, a, b))
    return out


def _spellings(key_plate, src):
    """The plate as this provider spells it in the stored positions (one or two)."""
    got = {r[0] for r in db.session.query(GpsPing.plate).filter(GpsPing.source == src)
           .filter(GpsPing.plate.like("%" + key_plate[-4:] + "%")).distinct().all()}
    return [p for p in got if gi._norm_plate(p) == key_plate] or [key_plate]


def _provider_plate(key_plate):
    t = next((t for t in Truck.query.all() if gi._norm_plate(t.plate) == key_plate), None)
    return t.plate if t else key_plate


def _due(plate, src, a, b, now_utc):
    """Ask about this hole? -> (yes, the record to update or None)."""
    rec = (GpsGapFill.query.filter_by(plate=plate, source=src, gap_from=a)
           .order_by(GpsGapFill.id.desc()).first())
    if rec is None:
        # Inside a span already asked about: what the history had there is
        # stored, and what is left is a real silence (12:35-19:41 after a
        # mine visit filled from 01:10). Asked again only on the retry rules.
        rec = (GpsGapFill.query.filter(GpsGapFill.plate == plate, GpsGapFill.source == src,
                                       GpsGapFill.gap_from <= a + EDGE, GpsGapFill.gap_to >= b - EDGE)
               .order_by(GpsGapFill.id.desc()).first())
        if rec is not None and rec.got:
            return False, rec
    if rec is None:
        return True, None
    if rec.got:
        # Filled before. A hole still open at the end of the window (the
        # truck is silent right now) can grow: ask again for the newer part.
        return (b > rec.gap_to + GAP_MIN and now_utc - rec.tried_at > RETRY_AFTER), rec
    recent = (_local_now() - b) < RETRY_WINDOW
    return (recent and (rec.tries or 0) < RETRY_TIMES and now_utc - rec.tried_at > RETRY_AFTER), rec


def fill(app, since, until=None, budget_s=240, only=None, dry=False, log=print):
    """Fill the holes between `since` and `until` (local time) for every truck,
    newest hole first, until `budget_s` seconds are spent. -> summary dict."""
    cfg = app.config.get("_GPS_CFG") or {}
    until = until or _local_now()
    t0, now_utc = time.time(), datetime.utcnow()
    todo = []
    for k, key in trucks(since):
        if only and k not in only:
            continue
        pcfg = cfg.get(key) or {}
        if not gi.provider_ready(pcfg, key):
            continue
        for plate, a, b in find_gaps(k, key, since, until):
            todo.append((b, k, key, plate, a))
    todo.sort(reverse=True)                     # newest first: today's report first
    done = {"holes": len(todo), "asked": 0, "added": 0, "skipped": 0, "errors": 0,
            "days": set(), "out_of_time": False}
    for b, k, key, plate, a in todo:
        if time.time() - t0 > budget_s:
            done["out_of_time"] = True
            break
        src = "api:" + key
        go, rec = _due(plate, src, a, b, now_utc)
        if not go:
            done["skipped"] += 1
            continue
        if dry:
            log("would ask %s %s %s -> %s" % (src, plate, a, b))
            done["asked"] += 1
            continue
        pts, errs, cur = [], [], a
        while cur < b and time.time() - t0 <= budget_s:
            ce = min(cur + CHUNK, b)
            try:
                got, e, _trunc = TRAILS[key](cfg[key], plate, cur, ce)
                pts += got
                errs += e
            except Exception as ex:  # noqa: BLE001 - one truck must not stop the run
                errs.append(gi._err_str(ex))
            cur = ce
        pings = []
        for p in pts:
            dt = gi._parse_dt(p.get("dt"))
            if dt is None or not (a + EDGE < dt < b - EDGE):
                continue                         # only the hole itself
            pings.append({"plate": plate, "dt": dt, "lat": p.get("lat"), "lng": p.get("lng"),
                          "speed": p.get("speed") or 0.0, "status": "history"})
        n = gi._store(pings, src) if pings else 0
        done["asked"] += 1
        done["added"] += n
        if errs:
            done["errors"] += 1
        if rec is None:
            rec = GpsGapFill(plate=plate, source=src, gap_from=a, gap_to=b, tries=0, got=0)
            db.session.add(rec)
        rec.gap_to, rec.tries, rec.tried_at = b, (rec.tries or 0) + 1, datetime.utcnow()
        rec.got = (rec.got or 0) + n
        rec.note = ("; ".join(sorted(set(errs)))[:200]) if errs else ("%d from history" % len(pts))[:200]
        db.session.commit()
        if n:
            for d in {p["dt"].strftime("%Y-%m-%d") for p in pings}:
                done["days"].add(d)
        log("%s %-10s %s -> %s  history %d, added %d%s" % (
            src, plate, a.strftime("%d/%m %H:%M"), b.strftime("%d/%m %H:%M"), len(pts), n,
            ("  (" + "; ".join(sorted(set(errs)))[:80] + ")") if errs else ""))
    done["days"] = sorted(done["days"])
    if done["days"] and not dry:
        done["stamped"] = restamp(done["days"])
    done["seconds"] = round(time.time() - t0)
    return done


def restamp(days):
    """Record the mine arrivals and the Monitor's actual times for these run
    days from the positions now stored - blanks only, like every pull does.
    A few days at a time, so a November-long refill never reads the whole
    ping table at once."""
    from . import actuals
    from .shift_routes import _visits_and_roles, _day_bounds
    days = sorted(set(days))
    n = m = 0
    for i in range(0, len(days), 3):
        chunk = days[i:i + 3]
        # The run day's window opens the day before and stays open three days:
        # stamp every run day whose window could hold the new positions.
        first = (datetime.strptime(chunk[0], "%Y-%m-%d") - timedelta(days=2)).strftime("%Y-%m-%d")
        run_days = sorted({(datetime.strptime(first, "%Y-%m-%d") + timedelta(days=j)).strftime("%Y-%m-%d")
                           for j in range((datetime.strptime(chunk[-1], "%Y-%m-%d")
                                           - datetime.strptime(first, "%Y-%m-%d")).days + 2)})
        since = _day_bounds(run_days[0])[0]
        visits, roles = _visits_and_roles(since=since)
        visits = [v for v in visits if v["enter"] >= since]
        n += actuals.stamp_days(run_days, visits, roles)
        m += actuals.record_arrivals(visits, roles)
        db.session.commit()
    return {"stamps": n, "mine_arrivals": m}
