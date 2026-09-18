import os
from datetime import timedelta


def _load_dotenv():
    """Minimal .env loader (no dependency). Reads KEY=VALUE lines from a .env
    file next to this config and sets any vars not already in the environment.
    Silent if the file is missing or malformed — never crashes startup."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass
    except Exception:
        pass


_load_dotenv()

DEFAULT_SECRET = "change-me-in-production"


def is_staging():
    """Whether this process is the sandbox. One definition, because the cookie
    name depends on it and a second opinion would split a login in half."""
    return (os.environ.get("COALAPP_ENV") or "").strip().lower() == "staging"


def _hours(name, default):
    """An hour count from the environment, ignoring anything unusable. A typo
    in a unit file must not stop the app booting."""
    try:
        n = int(str(os.environ.get(name) or "").strip())
        return n if n > 0 else default
    except ValueError:
        return default


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", DEFAULT_SECRET)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///coalapp.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Google Maps JavaScript API. Shared with the logistics platform, so the
    # key's referrer restriction has to allow this host too. Blank means the
    # capture map falls back to saying so rather than rendering a broken frame.
    GOOGLE_MAPS_KEY = os.environ.get("GOOGLE_MAPS_KEY", "")
    MAX_CONTENT_LENGTH = 64 * 1024 * 1024  # 64 MB uploads
    # A shift, not half an hour. Thirty minutes of idling signed people out in
    # the middle of a working day - the window slides on every request, so
    # touching the app at all keeps you in, and leaving it overnight does not.
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_hours("SESSION_HOURS", 12))
    SESSION_REFRESH_EACH_REQUEST = True     # sliding, from the last request
    # The logistics app shares this droplet's IP, browser cookies ignore ports,
    # and both apps default to a cookie named "session" — so each app kept
    # overwriting the other's login. A distinct name ends the fight.
    #
    # The sandbox needs its own name for exactly the same reason, and it is the
    # same droplet again: prod on :8080 and staging on :8082 are one cookie jar
    # to a browser, because a cookie is scoped by host and the port is not part
    # of it. Sharing the name meant each login overwrote the other's, and since
    # the two sign with different keys the overwritten one was not replaced but
    # unreadable - so every switch between the two tabs was a fresh login.
    SESSION_COOKIE_NAME = ("coalapp_staging_session" if is_staging()
                           else "coalapp_session")


def _truthy(v):
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def _plates(v):
    return [p.strip().upper() for p in str(v or "").replace(";", ",").split(",") if p.strip()]


def gps_providers_config():
    """GPS ingestion config, read from env / .env. A provider only becomes active
    when *_ENABLED is truthy AND its credentials are present. Everything is OFF by
    default, so this is inert until a .env is filled in on the server."""
    return {
        "tct": {
            "enabled": _truthy(os.environ.get("GPS_TCT_ENABLED")),
            "base_url": os.environ.get("GPS_TCT_BASE_URL", "http://webapi.dientutct.com/apiwba").rstrip("/"),
            # TCT uses HTTP Basic Auth. New names preferred; fall back to the old ones.
            "username": os.environ.get("GPS_TCT_USERNAME") or os.environ.get("GPS_TCT_CUSTOMER_CODE", ""),
            "password": os.environ.get("GPS_TCT_PASSWORD") or os.environ.get("GPS_TCT_KEY", ""),
            "auth_mode": os.environ.get("GPS_TCT_AUTH_MODE", "basic").strip().lower(),   # basic (confirmed) | body | header
            "timestamp_field": os.environ.get("GPS_TCT_TS_FIELD", "LocalTime"),          # LocalTime (UTC+7) | UTCTime
            "plates": _plates(os.environ.get("GPS_TCT_PLATES")),                          # blank = all authorised vehicles
        },
        # A SECOND TCT account. TCT moved the camera-package trucks onto their
        # own CustomerCode (46354, Sep 2026) and one login cannot see both
        # lists, so this account is pulled alongside the first.
        "tct2": {
            "enabled": _truthy(os.environ.get("GPS_TCT2_ENABLED")),
            "base_url": os.environ.get("GPS_TCT2_BASE_URL", "http://webapi.dientutct.com/apiwba").rstrip("/"),
            "username": os.environ.get("GPS_TCT2_USERNAME") or os.environ.get("GPS_TCT2_CUSTOMER_CODE", ""),
            "password": os.environ.get("GPS_TCT2_PASSWORD") or os.environ.get("GPS_TCT2_KEY", ""),
            "auth_mode": os.environ.get("GPS_TCT2_AUTH_MODE", "basic").strip().lower(),
            "timestamp_field": os.environ.get("GPS_TCT2_TS_FIELD", "LocalTime"),
            "plates": _plates(os.environ.get("GPS_TCT2_PLATES")),
        },
        # Viettel vTracking 2.0 Open API. Header auth (APIKey), one POST returns
        # the current position of every plate asked for. Served from a bare IP
        # with a self-signed certificate, so TLS verification cannot succeed and
        # is off for this host only; turn it on if Viettel publish a real one.
        "viettel": {
            "enabled": _truthy(os.environ.get("GPS_VIETTEL_ENABLED")),
            "base_url": os.environ.get("GPS_VIETTEL_BASE_URL", "https://171.229.16.202:8443").rstrip("/"),
            "api_key": os.environ.get("GPS_VIETTEL_KEY", ""),
            "verify_tls": _truthy(os.environ.get("GPS_VIETTEL_VERIFY_TLS")),
            "plates": _plates(os.environ.get("GPS_VIETTEL_PLATES")),   # blank = every vehicle on the account
        },
        "adsun": {
            "enabled": _truthy(os.environ.get("GPS_ADSUN_ENABLED")),
            "base_url": os.environ.get("GPS_ADSUN_BASE_URL", "https://shareapi.adsun.vn").rstrip("/"),
            "username": os.environ.get("GPS_ADSUN_USERNAME", ""),   # ShareAPI account (not the portal login)
            "password": os.environ.get("GPS_ADSUN_PASSWORD", ""),
            "auth_mode": os.environ.get("GPS_ADSUN_AUTH_MODE", "basic").strip().lower(),  # basic | query
            "plates": _plates(os.environ.get("GPS_ADSUN_PLATES")),   # blank = all authorised vehicles
        },
    }
