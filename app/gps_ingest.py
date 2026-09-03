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
import ssl
import time
import base64
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta

from .models import db, GpsPing, GpsIngestRun

# Operation timezone (Indochina, UTC+7). Server stores run times in UTC; the page
# shows them in local time so they match the provider ping times (already UTC+7).
_TZ_OFFSET = timedelta(hours=7)


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
                "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M",
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


def _ssl_ctx(verify):
    """Viettel serve from a bare IP under a self-signed certificate, so the
    handshake cannot be verified. Scoped to the call that asks for it rather
    than disabled globally."""
    if verify:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _http_post_json(url, payload, headers=None, timeout=45, insecure=False):
    data = json.dumps(payload or {}).encode("utf-8")
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx(not insecure)) as resp:
        raw = resp.read().decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except Exception:
        return {"_raw": raw[:2000]}


def _http_get_json(url, headers=None, timeout=45, insecure=False):
    h = {"Accept": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h, method="GET")
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx(not insecure)) as resp:
        raw = resp.read().decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except Exception:
        return {"_raw": raw[:2000]}


# ── connectors ───────────────────────────────────────────────────────────────
# Each returns a list of dicts: {plate, dt(datetime), lat, lng, speed, status}
# May raise on hard failure; the runner records the error on the run row.

def _tct_request(cfg):
    """Build the TCT /gps/tracking request (url, body, headers).
    Confirmed via TCT's Postman collection: the API uses HTTP Basic Auth
    (GPS_TCT_AUTH_MODE=basic, the default). `body`/`header` modes are kept only
    as fallbacks for experimentation."""
    url = cfg["base_url"] + "/gps/tracking"
    body = {"IsFuel": False}
    headers = {}
    user = cfg.get("username", "")
    pw = cfg.get("password", "")
    mode = cfg.get("auth_mode", "basic")
    if mode == "header":
        headers["CustomerCode"] = user
        headers["Key"] = pw
    elif mode == "body":
        body["CustomerCode"] = user
        body["Key"] = pw
    else:  # basic (default, confirmed) — HTTP Basic Authentication
        tok = base64.b64encode((user + ":" + pw).encode("utf-8")).decode("ascii")
        headers["Authorization"] = "Basic " + tok
    return url, body, headers


def _fetch_tct(cfg):
    """TCT 'Online data': current position of every authorised vehicle."""
    url, body, headers = _tct_request(cfg)
    data = _http_post_json(url, body, headers)
    if not isinstance(data, dict):
        raise RuntimeError("TCT: unexpected response (not a JSON object)")
    if "Access Denied" in str(data.get("MessageResult", "")):
        raise RuntimeError("TCT Access Denied — check CustomerCode/Key or GPS_TCT_AUTH_MODE")

    vehicles = _tct_vehicles(data)
    if vehicles is None:
        rc = data.get("ReturnCode")
        raise RuntimeError(
            "TCT returned no vehicle list (ReturnCode=%s, ObjectReturn=%s). "
            "Ask TCT what ReturnCode %s means and confirm the Key's authorised vehicles."
            % (rc, type(data.get("ObjectReturn")).__name__, rc))
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


def _adsun_request(cfg):
    """Build the Adsun ShareAPI 'GpsInfos' request (url, headers).
    API 1 returns the latest status of every authorised vehicle in one call.
    Auth: Basic (recommended) or username/pwd query params (GPS_ADSUN_AUTH_MODE)."""
    base = cfg["base_url"] + "/Vehicle/GpsInfos"
    user = cfg.get("username", "")
    pw = cfg.get("password", "")
    headers = {}
    if cfg.get("auth_mode", "basic") == "query":
        url = base + "?username=" + urllib.parse.quote(user) + "&pwd=" + urllib.parse.quote(pw)
    else:  # basic (recommended) — credentials in the Authorization header
        url = base
        tok = base64.b64encode((user + ":" + pw).encode("utf-8")).decode("ascii")
        headers["Authorization"] = "Basic " + tok
    return url, headers


def _fetch_adsun(cfg):
    """Adsun ShareAPI API 1 (GpsInfos): latest status of all authorised vehicles."""
    url, headers = _adsun_request(cfg)
    data = _http_get_json(url, headers)
    if not isinstance(data, dict):
        raise RuntimeError("Adsun: unexpected response (not a JSON object)")
    rows = data.get("Data")
    if not isinstance(rows, list):
        raise RuntimeError("Adsun returned no Data array (keys=%s)" % (list(data.keys()) if isinstance(data, dict) else None))
    want = set(cfg.get("plates") or [])
    out = []
    for v in rows:
        plate = v.get("Plate")
        if want and _norm_plate(plate) not in want:
            continue
        # Adsun advises discarding positions when Gps is false (low reliability).
        if v.get("Gps") is False:
            continue
        dt = _parse_dt(v.get("TimeUpdate"))
        lat = _num(v.get("Lat"))
        lng = _num(v.get("Lng"))
        if dt is None or lat is None or lng is None:
            continue
        out.append({
            "plate": str(plate).strip(),
            "dt": dt, "lat": lat, "lng": lng,
            "speed": _num(v.get("Speed")) or 0.0,
            "status": ("stopped" if v.get("IsStop") else "moving"),
        })
    return out


def _viettel_search(cfg, plates=None, attributes=("datas",)):
    """One POST to vTracking's vehicle/search. Returns the raw vehicles list.

    The plate filter is applied by Viettel, not here: the account can see the
    whole Phonesack Vietnam fleet, and the project has no business pulling
    vehicles that are not on it.
    """
    url = cfg["base_url"] + "/api/v1/vtracking/vehicle/search?limit=500"
    body = {"attributes": list(attributes)}
    want = list(plates if plates is not None else (cfg.get("plates") or []))
    if want:
        body["plates"] = want
    headers = {"APIKey": cfg.get("api_key", "")}
    data = _http_post_json(url, body, headers,
                           insecure=not cfg.get("verify_tls"))
    if not isinstance(data, dict):
        raise RuntimeError("Viettel: unexpected response (not a JSON object)")
    vehicles = data.get("vehicles")
    if not isinstance(vehicles, list):
        raise RuntimeError("Viettel returned no vehicles array (keys=%s)"
                           % sorted(data.keys())[:6])
    return vehicles


def _viettel_datas(vehicle):
    """The 'datas' attribute of one vehicle: position, speed and status."""
    for a in vehicle.get("attributes") or []:
        if a.get("attribute_key") == "datas" and isinstance(a.get("value"), dict):
            return a["value"], a.get("last_update_ts")
    return None, None


def _viettel_dt(value, last_update_ts):
    """Epoch milliseconds -> the naive UTC+7 datetime the other providers store.

    TCT is read from its LocalTime field and Adsun from TimeUpdate, both already
    Indochina time, and the capture page shows ping times unshifted. Viettel
    sends epoch ms, which is UTC, so it is moved to the same footing here -
    otherwise its trucks would sit seven hours behind the rest of the board.
    """
    ms = value.get("timestamp") or last_update_ts
    if not ms:
        return None
    try:
        return datetime.utcfromtimestamp(float(ms) / 1000.0) + _TZ_OFFSET
    except Exception:
        return None


def _fetch_viettel(cfg):
    """Viettel vTracking: current position of each vehicle on the plate list."""
    out = []
    for v in _viettel_search(cfg):
        plate = v.get("license_plate")
        value, last_ts = _viettel_datas(v)
        if not plate or not isinstance(value, dict):
            continue
        # badgps means the fix itself is unreliable - the same reason Adsun
        # positions are dropped when its Gps flag is false.
        raw_status = str(value.get("status") or "").lower()
        if raw_status == "badgps":
            continue
        dt = _viettel_dt(value, last_ts)
        lat = _num(value.get("latitude"))
        lng = _num(value.get("longitude"))
        if dt is None or lat is None or lng is None:
            continue
        out.append({
            "plate": str(plate).strip(),
            "dt": dt, "lat": lat, "lng": lng,
            "speed": _num(value.get("speed")) or 0.0,
            "status": "moving" if raw_status == "run" else (raw_status or "stopped"),
        })
    return out


def _tct_vehicles(data):
    """Locate the vehicle list across TCT envelopes. Their doc shows
    {MessageResult, Vehicles:[...]}, but the live API returns
    {ReturnCode, ObjectReturn:<list|obj|null>}. Returns a list, or None when no
    list is present (e.g. ObjectReturn is null)."""
    v = data.get("Vehicles")                       # documented envelope
    if isinstance(v, list):
        return v
    obj = data.get("ObjectReturn")                 # observed envelope
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("Vehicles", "List", "Data", "Items", "Result"):
            if isinstance(obj.get(k), list):
                return obj[k]
        return [obj]                               # a single vehicle object
    return None


_CONNECTORS = {"tct": _fetch_tct, "viettel": _fetch_viettel, "adsun": _fetch_adsun}


# ── runner / storage ─────────────────────────────────────────────────────────

def provider_ready(cfg, key):
    if not cfg.get("enabled"):
        return False
    if key == "tct":
        return bool(cfg.get("base_url") and cfg.get("username") and cfg.get("password"))
    if key == "adsun":
        return bool(cfg.get("base_url") and cfg.get("username") and cfg.get("password"))
    if key == "viettel":
        return bool(cfg.get("base_url") and cfg.get("api_key"))
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


def debug_provider(app, key):
    """Admin diagnostic: make the raw provider call and summarise the response
    (top-level keys, MessageResult, vehicle count, first-vehicle field names) so
    'no authorised vehicles' can be told apart from a response-shape mismatch.
    Reads nothing sensitive back (credentials are in the request, not the reply).
    Never raises."""
    cfg = (app.config.get("_GPS_CFG") or {})
    pcfg = cfg.get(key) or {}
    if not provider_ready(pcfg, key):
        return {"ok": False, "error": "provider not enabled / missing credentials"}
    try:
        if key == "tct":
            url, body, headers = _tct_request(pcfg)
            data = _http_post_json(url, body, headers)
        elif key == "adsun":
            url, headers = _adsun_request(pcfg)
            data = _http_get_json(url, headers)
        else:
            return {"ok": False, "error": "no debug available for this provider yet"}
    except urllib.error.URLError as e:
        return {"ok": False, "error": "network: " + str(getattr(e, "reason", e))}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": type(e).__name__ + ": " + str(e)}

    info = {"ok": True}
    if isinstance(data, dict):
        info["top_keys"] = list(data.keys())
        info["message_result"] = data.get("MessageResult") or data.get("Description")
        info["return_code"] = data.get("ReturnCode") if data.get("ReturnCode") is not None else data.get("Status")
        if key == "adsun":
            veh = data.get("Data") if isinstance(data.get("Data"), list) else None
        else:
            veh = _tct_vehicles(data)
        info["vehicles_count"] = len(veh) if isinstance(veh, list) else None
        if isinstance(veh, list) and veh and isinstance(veh[0], dict):
            info["first_vehicle_keys"] = list(veh[0].keys())[:25]
        info["raw_snippet"] = json.dumps(data)[:1200]
    else:
        info["raw_snippet"] = str(data)[:1200]
    return info


def latest_points(app):
    """Latest stored position per (plate, source) for api:* sources — for the map."""
    from sqlalchemy import func
    sub = (db.session.query(GpsPing.plate, GpsPing.source, func.max(GpsPing.dt).label("mx"))
           .filter(GpsPing.source.like("api:%"))
           .group_by(GpsPing.plate, GpsPing.source).subquery())
    q = (db.session.query(GpsPing)
         .join(sub, (GpsPing.plate == sub.c.plate) &
                    (GpsPing.source == sub.c.source) &
                    (GpsPing.dt == sub.c.mx)))
    out, seen = [], set()
    for g in q.all():
        k = (g.plate, g.source)
        if k in seen:
            continue
        seen.add(k)
        out.append({"plate": g.plate, "lat": g.lat, "lng": g.lng,
                    "dt": g.dt.strftime("%Y-%m-%d %H:%M:%S") if g.dt else None,
                    "speed": g.speed, "status": g.status, "source": g.source})
    return out


def _basic_headers(user, pw):
    tok = base64.b64encode((user + ":" + pw).encode("utf-8")).decode("ascii")
    return {"Authorization": "Basic " + tok}


# Trail limits: cap the requested range, page it in provider-sized windows, and
# stop before the web worker's own timeout would kill the request. A window that
# errors is skipped and reported, so one bad call cannot sink the whole trail.
# Per-provider range caps. TCT pages 24h windows back-to-back without complaint.
# Adsun caps a history query at ~3 days AND rate-limits successive calls (the
# guide says 10s; measured ~30s), so an Adsun trail is a single call per click.
TRAIL_MAX_DAYS = {"tct": 14, "viettel": 7, "adsun": 3}
_TRAIL_DEADLINE_S = 25     # stop paging after this many seconds, return partial
_TRAIL_CALL_TIMEOUT = 12   # per provider call


def _err_str(e):
    if isinstance(e, urllib.error.HTTPError):
        if e.code == 429:
            return "provider rate limit — wait about 30 seconds and try again"
        return ("HTTP %s %s" % (e.code, e.reason or "")).strip()
    if isinstance(e, urllib.error.URLError):
        return str(e.reason or e) or "connection failed"
    return (type(e).__name__ + ": " + str(e)).strip()


def _trail_paged(begin, end, window, fetch_window, gap_s=0):
    """Walk [begin, end) in `window`-sized chunks calling fetch_window(cur, ce),
    sleeping gap_s between chunks (provider rate limits). Returns
    (points, errors, truncated)."""
    pts, errors = [], []
    cur, deadline = begin, time.time() + _TRAIL_DEADLINE_S
    truncated, first = False, True
    while cur < end:
        if not first and gap_s:
            if time.time() + gap_s > deadline:
                truncated = True
                break
            time.sleep(gap_s)
        if time.time() > deadline:
            truncated = True
            break
        first = False
        ce = min(cur + window, end)
        try:
            pts.extend(fetch_window(cur, ce))
        except Exception as e:  # noqa: BLE001 - keep going; report per window
            errors.append(_err_str(e))
        cur = ce
    pts.sort(key=lambda p: p["dt"])
    return pts, errors, truncated


def _trail_tct(pcfg, plate, begin, end):
    """TCT route history (POST /gps/route) — max 24h per call, so page by day."""
    url = pcfg["base_url"] + "/gps/route"
    headers = _basic_headers(pcfg.get("username", ""), pcfg.get("password", ""))

    def fetch_window(cur, ce):
        body = {"vehiclePlate": plate,
                "fromDate": cur.strftime("%Y-%m-%d %H:%M:%S"),
                "toDate": ce.strftime("%Y-%m-%d %H:%M:%S")}
        data = _http_post_json(url, body, headers, timeout=_TRAIL_CALL_TIMEOUT)
        rows = data.get("Routes") if isinstance(data, dict) else None
        if not isinstance(rows, list) and isinstance(data, dict):
            rows = data.get("ObjectReturn") if isinstance(data.get("ObjectReturn"), list) else []
        out = []
        for r in (rows or []):
            dt = _parse_dt(r.get("LocalTime") or r.get("UTCTime"))
            lat = _num(r.get("Latitude")); lng = _num(r.get("Longitude"))
            if dt and lat is not None and lng is not None:
                out.append({"dt": dt.strftime("%Y-%m-%d %H:%M:%S"), "lat": lat, "lng": lng, "speed": _num(r.get("Speed")) or 0.0})
        return out

    return _trail_paged(begin, end, timedelta(hours=24), fetch_window)


def _trail_adsun(pcfg, plate, begin, end):
    """Adsun trip history (GET /Vehicle/GpsHistoryV3). One call per trail: the
    range cap (3 days) guarantees a single window, because Adsun rate-limits
    successive history calls far harder than documented (~30s, measured)."""
    headers = _basic_headers(pcfg.get("username", ""), pcfg.get("password", ""))

    def fetch_window(cur, ce):
        q = ("?licensePlate=" + urllib.parse.quote(plate)
             + "&beginTime=" + urllib.parse.quote(cur.strftime("%Y-%m-%d %H:%M:%S"))
             + "&endTime=" + urllib.parse.quote(ce.strftime("%Y-%m-%d %H:%M:%S")))
        data = _http_get_json(pcfg["base_url"] + "/Vehicle/GpsHistoryV3" + q, headers,
                              timeout=_TRAIL_CALL_TIMEOUT)
        rows = data.get("Data") if isinstance(data, dict) and isinstance(data.get("Data"), list) else []
        out = []
        for r in rows:
            dt = _parse_dt(r.get("UpdateTime"))
            lat = _num(r.get("Lat")); lng = _num(r.get("Lng"))
            if dt and lat is not None and lng is not None:
                out.append({"dt": dt.strftime("%Y-%m-%d %H:%M:%S"), "lat": lat, "lng": lng, "speed": _num(r.get("Speed")) or 0.0})
        return out

    return _trail_paged(begin, end, timedelta(days=3), fetch_window)


def _trail_viettel(pcfg, plate, begin, end):
    """Viettel journey history. The endpoint is keyed on the vehicle's id, not
    its plate, so the plate is resolved through vehicle/search first. Results
    are paged with the 'after' cursor the response hands back."""
    vehicles = _viettel_search(pcfg, plates=[plate], attributes=())
    vid = None
    for v in vehicles:
        if _norm_plate(v.get("license_plate")) == _norm_plate(plate):
            vid = v.get("id")
            break
    if not vid:
        return [], ["plate not found on the Viettel account"], False

    headers = {"APIKey": pcfg.get("api_key", "")}
    insecure = not pcfg.get("verify_tls")
    # The API takes epoch ms in UTC; the caller works in Indochina time.
    start_ms = int((begin - _TZ_OFFSET).timestamp() * 1000)
    end_ms = int((end - _TZ_OFFSET).timestamp() * 1000)

    pts, errors, after, deadline = [], [], None, time.time() + _TRAIL_DEADLINE_S
    while True:
        q = ("/api/v1/vtracking/vehicle/journey/" + urllib.parse.quote(str(vid))
             + "?limit=500&startTime=%d&endTime=%d" % (start_ms, end_ms))
        if after:
            q += "&after=" + urllib.parse.quote(after)
        try:
            data = _http_get_json(pcfg["base_url"] + q, headers,
                                  timeout=_TRAIL_CALL_TIMEOUT, insecure=insecure)
        except Exception as e:  # noqa: BLE001
            errors.append(_err_str(e))
            break
        logs = data.get("logs") if isinstance(data, dict) else None
        for r in (logs or []):
            val = r.get("value")
            if not isinstance(val, dict):
                continue
            dt = _viettel_dt({"timestamp": r.get("ts")}, r.get("ts"))
            lat, lng = _num(val.get("latitude")), _num(val.get("longitude"))
            if dt and lat is not None and lng is not None:
                pts.append({"dt": dt.strftime("%Y-%m-%d %H:%M:%S"), "lat": lat,
                            "lng": lng, "speed": _num(val.get("speed")) or 0.0})
        after = (data or {}).get("after")
        if not after or not logs:
            return pts, errors, False
        if time.time() > deadline:
            return pts, errors, True


def fetch_trail(app, source, plate, begin, end):
    """On-demand breadcrumb trail for one truck over a time range (not stored)."""
    cfg = (app.config.get("_GPS_CFG") or {})
    src = source or ""
    key = ("adsun" if "adsun" in src else
           "viettel" if "viettel" in src else
           "tct" if "tct" in src else None)
    if not key:
        return {"ok": False, "error": "unknown source"}
    pcfg = cfg.get(key) or {}
    if not provider_ready(pcfg, key):
        return {"ok": False, "error": "provider not enabled / missing credentials"}
    max_days = TRAIL_MAX_DAYS.get(key, 3)
    if (end - begin) > timedelta(days=max_days):
        return {"ok": False,
                "error": "range too long for %s — choose %d days or fewer per trail" % (key.upper(), max_days)}
    try:
        fn = {"tct": _trail_tct, "adsun": _trail_adsun,
              "viettel": _trail_viettel}[key]
        pts, errors, truncated = fn(pcfg, plate, begin, end)
        note_bits = []
        if errors:
            uniq = sorted(set(errors))
            note_bits.append("%d window(s) failed: %s" % (len(errors), "; ".join(uniq[:3])))
        if truncated:
            note_bits.append("stopped early at the %ds time budget — narrow the range for the rest" % _TRAIL_DEADLINE_S)
        out = {"ok": True, "plate": plate, "source": source, "count": len(pts), "points": pts}
        if note_bits:
            out["note"] = " · ".join(note_bits)
        return out
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": _err_str(e)}


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
            "last_run": (last.finished + _TZ_OFFSET).strftime("%Y-%m-%d %H:%M") if last and last.finished else None,
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
