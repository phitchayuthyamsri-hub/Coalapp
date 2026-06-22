"""Usage analytics: client IP, country geolocation, login recording.

Geolocation is done in a background thread so a slow/blocked network can
never delay (or hang) the login request.
"""
import json
import socket
import threading
import urllib.request

from flask import current_app

from .models import db, LoginEvent

_geo_cache = {}


def client_ip(req):
    xff = req.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return req.remote_addr or ""


def geolocate(ip):
    if not ip or ip.startswith("127.") or ip == "::1" or ip.startswith("10.") or ip.startswith("192.168."):
        return ("Local network", "LO")
    if ip in _geo_cache:
        return _geo_cache[ip]
    res = ("Unknown", "")
    try:
        url = "http://ip-api.com/json/%s?fields=country,countryCode" % ip
        with urllib.request.urlopen(url, timeout=2.0) as r:
            d = json.loads(r.read().decode("utf-8"))
            res = (d.get("country") or "Unknown", d.get("countryCode") or "")
    except Exception:
        res = ("Unknown", "")
    _geo_cache[ip] = res
    return res


def _resolve_country_bg(app, event_id, ip):
    """Runs in a daemon thread; never blocks the request."""
    socket.setdefaulttimeout(3)
    country, code = geolocate(ip)
    if country and country not in ("Unknown",):
        try:
            with app.app_context():
                ev = db.session.get(LoginEvent, event_id)
                if ev:
                    ev.country = country
                    ev.country_code = code
                    db.session.commit()
        except Exception:
            pass


def record_login(user, req):
    """Record the login immediately; resolve country in the background."""
    try:
        ip = client_ip(req)
        # Fast path: local IPs resolve instantly with no network call.
        if not ip or ip.startswith(("127.", "10.", "192.168.")) or ip in ("::1",):
            country, code = ("Local network", "LO")
        else:
            country, code = ("Unknown", "")  # filled in by background thread
        ev = LoginEvent(user_id=user.id, username=user.username,
                        ip=ip, country=country, country_code=code)
        db.session.add(ev)
        db.session.commit()
        if country == "Unknown" and ip:
            app = current_app._get_current_object()
            threading.Thread(target=_resolve_country_bg, args=(app, ev.id, ip),
                             daemon=True).start()
    except Exception:
        db.session.rollback()
