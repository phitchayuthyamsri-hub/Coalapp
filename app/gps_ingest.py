"""
GPS ingestion engine (provider-agnostic).

Pulls vehicle positions from a provider's API and stores them as GpsPing rows.
Stdlib-only (urllib) so importing this module can NEVER crash app startup, and
everything is OFF unless configured in a server-side .env.

Providers:
  - tct   : POST {base}/gps/tracking   -> live positions of the account's vehicles
  - adsun : ShareAPI (REST GET)         -> history by plate+range (wire up when docs arrive)

Nothing here runs on its own. It is triggered by:
  - gps_pull.py           (cron / manual, on the server)
  - the "Pull now" button on /gps-capture  (admin only)

Field mapping is done from the vendor docs; the network/auth details that the
docs left unclear are read from config so they can be corrected without a code
change (see GPS_TCT_AUTH_MODE etc.).
"""
import json
import base64
import urllib.request
import urllib.error
from datetime import datetime

from .models import db, GpsPing, GpsIngestRun


# ── helpers ──────────────────────────────────────────────────────────────────

def _norm_plate(p):
    return "".join(ch for ch in str(p or "").upper() if ch.isalnum())


def _parse_dt(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    s = str(v).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(s[:len(fmt) + 4].strip(), fmt)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _num(v):
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return None


def _http_post_json(url, payload, headers=None, timeout=45):
    data = json.dumps(payload or {}).encode("utf-8")
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except Exception:
        return {"_raw": raw[:2000]}


# ── connectors ───────────────────────────────────────────────────────────────
# Each returns a list of dicts: {plate, dt(datetime), lat, lng, speed, status}
# May raise on hard failure; the runner records the error on the run row.

def _fetch_tct(cfg):
    """TCT 'Online data': current position of every vehicle the Key is authorised
    for. TCT grants access via a CustomerCode + Key (per their "License" section).
    Whether they travel in the body or as headers is configurable:
      GPS_TCT_AUTH_MODE = body (default) | header
    Adjust if the first pull returns Access Denied — no code change needed.
    """
    url = cfg["base_url"] + "/gps/tracking"
    body = {"IsFuel": False}
    headers = {}
    cc = cfg.get("customer_code", "")
    api_key = cfg.get("key", "")
    mode = cfg.get("auth_mode", "body")
    if mode == "header":
        headers["CustomerCode"] = cc
        headers["Key"] = api_key
    else:  # body (default): CustomerCode + Key travel in the request body
        body["CustomerCode"] = cc
        body["Key"] = api_key

    data = _http_post_json(url, body, headers)
    msg = str(data.get("MessageResult", "")) if isinstance(data, dict) else ""
    if "Access Denied" in msg:
        raise RuntimeError("TCT returned Access Denied — check credentials / GPS_TCT_AUTH_MODE")

    vehicles = (data or {}).get("Vehicles") or []
    tsf = cfg.get("timestamp_field", "LocalTime")
    want = set(cfg.get("plates") or [])
    out = []
    for v in vehicles:
        plate = v.get("VehiclePlate")
        if want and _norm_plate(plate) not in want:
            continue
        dt = _parse_dt(v.get(tsf) or v.get("LocalTime") or v.get("UTCTime"))
        lat = _num(v.get("Latitude"))
        lng = _num(v.get("Longitude"))
        if dt is None or lat is None or lng is None:
            continue
        out.append({
            "plate": str(plate).strip(),
            "dt": dt, "lat": lat, "lng": lng,
            "speed": _num(v.get("Speed")) or 0.0,
            "status": str(v.get("State", "")),
        })
    return out


def _fetch_adsun(cfg):
    """Adsun ShareAPI (REST). Placeholder until the ShareAPI docs + credentials
    arrive; returns [] so a poll is a harmless no-op in the meantime."""
    if not cfg.get("base_url") or not cfg.get("token"):
        return []
    # TODO: implement per Adsun ShareAPI docs — GET history by vehicle + time
    # range (max 3 days/call, min 5s interval), map plate/time/lat/lng/speed.
    return []


_CONNECTORS = {"tct": _fetch_tct, "adsun": _fetch_adsun}


# ── runner / storage ─────────────────────────────────────────────────────────

def provider_ready(cfg, key):
    if not cfg.get("enabled"):
        return False
    if key == "tct":
        return bool(cfg.get("base_url") and cfg.get("customer_code") and cfg.get("key"))
    if key == "adsun":
        return bool(cfg.get("base_url") and cfg.get("token"))
    return False


def _store(pings, source):
    """Insert new pings, skipping (plate, dt) duplicates already stored for this
    source (idempotent — safe to re-poll overlapping windows)."""
    if not pings:
        return 0
    dts = [p["dt"] for p in pings]
    lo, hi = min(dts), max(dts)
    plates = list({p["plate"] for p in pings})
    existing = set()
    for r in GpsPing.query.filter(GpsPing.source == source,
                                  GpsPing.dt >= lo, GpsPing.dt <= hi,
                                  GpsPing.plate.in_(plates)).all():
        existing.add((r.plate, r.dt))
    n = 0
    for p in pings:
        key = (p["plate"], p["dt"])
        if key in existing:
            continue
        db.session.add(GpsPing(plate=p["plate"], dt=p["dt"], lat=p["lat"],
                               lng=p["lng"], speed=p.get("speed") or 0.0,
                               status=p.get("status", ""), source=source))
        existing.add(key)
        n += 1
    db.session.commit()
    return n


def run_provider(app, key):
    """Run one provider inside an app context. Returns a result dict and never
    raises — any failure is recorded on the GpsIngestRun row."""
    cfg = (app.config.get("_GPS_CFG") or {})
    pcfg = (cfg.get(key) or {})
    source = "api:" + key
    run = GpsIngestRun(provider=key, source=source, started=datetime.utcnow())
    fetched = inserted = 0
    err = ""
    try:
        if key not in _CONNECTORS:
            err = "unknown provider"
        elif not provider_ready(pcfg, key):
            err = "provider not enabled / missing credentials"
        else:
            pings = _CONNECTORS[key](pcfg)
            fetched = len(pings)
            inserted = _store(pings, source)
    except urllib.error.URLError as e:
        err = "network: " + str(getattr(e, "reason", e))
    except Exception as e:  # noqa: BLE001 - deliberately swallow so a poll can't crash
        err = type(e).__name__ + ": " + str(e)
    run.finished = datetime.utcnow()
    run.fetched = fetched
    run.inserted = inserted
    run.error = err[:500]
    try:
        db.session.add(run)
        db.session.commit()
    except Exception:
        db.session.rollback()
    return {"provider": key, "fetched": fetched, "inserted": inserted, "error": err}


def run_all(app):
    cfg = (app.config.get("_GPS_CFG") or {})
    results = []
    for key in _CONNECTORS:
        if (cfg.get(key) or {}).get("enabled"):
            results.append(run_provider(app, key))
    return results


def status_summary(app):
    """Per-provider and per-truck capture status for the /gps-capture page."""
    from sqlalchemy import func
    cfg = (app.config.get("_GPS_CFG") or {})
    out = {"providers": [], "trucks": []}
    for key in _CONNECTORS:
        pcfg = cfg.get(key) or {}
        source = "api:" + key
        total = GpsPing.query.filter_by(source=source).count()
        last = GpsIngestRun.query.filter_by(provider=key).order_by(GpsIngestRun.id.desc()).first()
        out["providers"].append({
            "key": key,
            "enabled": bool(pcfg.get("enabled")),
            "ready": provider_ready(pcfg, key),
            "plates": pcfg.get("plates") or [],
            "total_pings": total,
            "last_run": last.finished.strftime("%Y-%m-%d %H:%M") if last and last.finished else None,
            "last_fetched": last.fetched if last else None,
            "last_inserted": last.inserted if last else None,
            "last_error": (last.error if last else "") or "",
        })
    rows = db.session.query(
        GpsPing.plate, GpsPing.source, func.max(GpsPing.dt), func.count(GpsPing.id)
    ).filter(GpsPing.source.like("api:%")).group_by(GpsPing.plate, GpsPing.source).all()
    for plate, source, last_dt, cnt in rows:
        out["trucks"].append({
            "plate": plate, "source": source,
            "last": last_dt.strftime("%Y-%m-%d %H:%M:%S") if last_dt else None,
            "count": cnt,
        })
    out["trucks"].sort(key=lambda r: (r["source"], r["plate"]))
    return out
