# -*- coding: utf-8 -*-
"""Adsun ShareAPI: the account's vehicle groups (pageIds) go on the request.

Run: python tests/test_adsun_page_ids.py   (PYTHONIOENCODING=utf-8 on Windows)

02/11/2026: PTS's ShareAPI link reads
/Vehicle/GpsInfos?pageIds=1019|1305|6196|7103&username=..&pwd=.. and answers
the shape this connector already parses (Plate, Lat, Lng, TimeUpdate
'2026/11/02 21:33:25', Gps, IsStop).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from app import gps_ingest as gi   # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


cfg = {"base_url": "https://shareapi.adsun.vn", "username": "acct", "password": "p w",
       "auth_mode": "query", "page_ids": ["1019", "1305", "6196", "7103"], "plates": []}
url, headers = gi._adsun_request(cfg)
check("query mode: groups, then the sign-in, on the URL", url,
      "https://shareapi.adsun.vn/Vehicle/GpsInfos?pageIds=1019%7C1305%7C6196%7C7103&username=acct&pwd=p%20w")
check("...and no Authorization header", headers, {})

url, headers = gi._adsun_request(dict(cfg, auth_mode="basic"))
check("basic mode: only the groups on the URL", url,
      "https://shareapi.adsun.vn/Vehicle/GpsInfos?pageIds=1019%7C1305%7C6196%7C7103")
check("...the sign-in in the header", "Authorization" in headers, True)

url, _ = gi._adsun_request(dict(cfg, page_ids=[], auth_mode="basic"))
check("no groups set: the bare address, as before", url, "https://shareapi.adsun.vn/Vehicle/GpsInfos")

# The reply as PTS's link gives it (trimmed).
gi._http_get_json = lambda url, headers=None, **k: {"Data": [
    {"Plate": "74H01966", "Lat": 16.6756878, "Lng": 107.260208, "Speed": 54.0, "Gps": True,
     "IsStop": False, "TimeUpdate": "2026/11/02 21:33:25", "Address": "Quốc lộ 1"},
    {"Plate": "74F00285", "Lat": 16.79598, "Lng": 107.08699, "Speed": 0.0, "Gps": True,
     "IsStop": True, "TimeUpdate": "2026/11/02 21:33:11"},
    {"Plate": "99H04224", "Lat": 16.42, "Lng": 107.54, "Gps": False,
     "IsStop": True, "TimeUpdate": "2026/10/31 22:46:20"}]}
pts = gi._fetch_adsun(dict(cfg, plates=["74H01966", "99H04224"]))
check("only the plates asked for, and no unreliable fix", [p["plate"] for p in pts], ["74H01966"])
check("...its time read as given (local)", str(pts[0]["dt"]), "2026-11-02 21:33:25")
check("...moving", pts[0]["status"], "moving")

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
