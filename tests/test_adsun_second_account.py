# -*- coding: utf-8 -*-
"""A second Adsun login is pulled alongside the first, as tct2 is for TCT.

Run: python tests/test_adsun_second_account.py   (PYTHONIOENCODING=utf-8 on Windows)

03/11/2026: Hoanh Son's 74H01136 is on its own ShareAPI login (group
quangtienqt), which PTS's login cannot see.
"""
import os
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

os.environ.update(GPS_ADSUN2_ENABLED="1", GPS_ADSUN2_USERNAME="acct2", GPS_ADSUN2_PASSWORD="pw",
                  GPS_ADSUN2_AUTH_MODE="query", GPS_ADSUN2_PAGE_IDS="1019",
                  GPS_ADSUN2_PLATES="74H01136")

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
c2 = cfg.get("adsun2") or {}
check("the second login is read from its own settings", c2.get("username"), "acct2")
check("...ready to pull", gi.provider_ready(c2, "adsun2"), True)
check("...a first login left blank is not", gi.provider_ready(dict(c2, username=""), "adsun2"), False)
check("...pulled by the Adsun connector", gi._CONNECTORS.get("adsun2") is gi._fetch_adsun, True)
url, _ = gi._adsun_request(c2)
check("...with its own groups and sign-in",
      url, "https://shareapi.adsun.vn/Vehicle/GpsInfos?pageIds=1019&username=acct2&pwd=pw")
check("its positions rank as Adsun", gi._provider_key("api:adsun2"), "adsun")

# A trail asked for on an api:adsun2 truck goes to the second login.
seen = {}


def fake_trail(pcfg, plate, begin, end):
    seen["user"] = pcfg.get("username")
    return [], [], False


gi._trail_adsun = fake_trail


class App:
    config = {"_GPS_CFG": cfg}


end = datetime(2026, 11, 3, 16, 0)
gi._stored_trail = lambda plate, b, e: []
gi.fetch_trail(App, "api:adsun2", "74H01136", end - timedelta(hours=6), end)
check("a trail for its truck goes to the second login", seen.get("user"), "acct2")

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
