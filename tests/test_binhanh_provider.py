# -*- coding: utf-8 -*-
"""Binh Anh GPS: read by the TCT connector at Binh Anh's address.

Run: python tests/test_binhanh_provider.py   (PYTHONIOENCODING=utf-8 on Windows)

03/11/2026: Binh Anh's API guide (for TNHH Phonesack Viet Nam) documents
POST /apiwba/gps/tracking and /gps/route with CustomerCode + Key as HTTP Basic,
returning {MessageResult, Vehicles:[{VehiclePlate, LocalTime, Latitude, ...}]}
- the platform TCT runs on. 67 of the three new subcontractors' trucks are on it.
"""
import os
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

os.environ.update(GPS_BINHANH2_ENABLED="1", GPS_BINHANH2_CUSTOMER_CODE="code2",
                  GPS_BINHANH2_KEY="key2", GPS_BINHANH2_PLATES="43H16225,37H09305")

from config import gps_providers_config   # noqa: E402
from app import gps_ingest as gi          # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


cfg = gps_providers_config()
c2 = cfg["binhanh2"]
check("three Binh Anh slots", all(k in cfg for k in gi.BINHANH_KEYS), True)
check("...an unset one is off", gi.provider_ready(cfg["binhanh"], "binhanh"), False)
check("the second is ready from its own settings", gi.provider_ready(c2, "binhanh2"), True)
url, body, headers = gi._tct_request(c2)
check("...asks Binh Anh's tracking address", url, "https://apigps.binhanh.vn/apiwba/gps/tracking")
check("...signs in with CustomerCode + Key (Basic)", headers.get("Authorization", "")[:6], "Basic ")

seen = {}


def fake_post(url, body, headers=None, **k):
    seen["url"] = url
    return {"MessageResult": "Success", "Vehicles": [
        {"VehiclePlate": "43H16225", "LocalTime": "2026-11-03T14:29:00", "UTCTime": "2026-11-03T07:29:00",
         "Latitude": 16.31, "Longitude": 106.97, "Speed": 40.0, "State": 3, "Address": "QL15D"},
        {"VehiclePlate": "43H99999", "LocalTime": "2026-11-03T14:29:00",
         "Latitude": 16.0, "Longitude": 107.0, "Speed": 0.0, "State": 1}]}


gi._http_post_json = fake_post
pts = gi._CONNECTORS["binhanh2"](c2)
check("only the account's plates we asked for", [p["plate"] for p in pts], ["43H16225"])
check("...at local time", str(pts[0]["dt"]), "2026-11-03 14:29:00")

check("the register's 'Bình Anh' ranks as Binh Anh", gi._provider_key("Bình Anh"), "binhanh")
check("...and so do its pings", gi._provider_key("api:binhanh2"), "binhanh")
check("TCT is still TCT", gi._provider_key("api:tct2"), "tct")


def fake_trail(pcfg, plate, begin, end):
    seen["trail_user"] = pcfg.get("username")
    seen["trail_base"] = pcfg.get("base_url")
    return [], [], False


gi._trail_tct = fake_trail
gi._stored_trail = lambda plate, b, e: []


class App:
    config = {"_GPS_CFG": cfg}


end = datetime(2026, 11, 3, 16, 0)
gi.fetch_trail(App, "api:binhanh2", "43H16225", end - timedelta(hours=6), end)
check("a trail on a binhanh2 truck asks that account", seen.get("trail_user"), "code2")
check("...at Binh Anh's address", seen.get("trail_base"), "https://apigps.binhanh.vn/apiwba")

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
