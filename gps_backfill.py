#!/usr/bin/env python3
"""
Fill the holes in captured GPS from each provider's route history (24/11/2026).
See app/gps_backfill.py for why.

Usage (on the server, from /opt/coalapp):
    python gps_backfill.py                      # the last 3 days, about 4 minutes of asking
    python gps_backfill.py --since 2026-11-01 --budget 3000   # a longer refill
    python gps_backfill.py --plate 20C21788 --since 2026-11-19
    python gps_backfill.py --dry                # list the holes it would ask about

Cron, every 15 minutes, never two at once:
    */15 * * * * cd /opt/coalapp && /usr/bin/flock -n /tmp/coalapp_backfill.lock ... gps_backfill.py
"""
import argparse
import sys
from datetime import datetime, timedelta

from app import create_app
from app import gps_backfill


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="YYYY-MM-DD, local time (default: 3 days back)")
    ap.add_argument("--budget", type=int, default=240, help="seconds of asking (default 240)")
    ap.add_argument("--plate", action="append", help="only this truck (repeatable)")
    ap.add_argument("--dry", action="store_true", help="list, do not ask or store")
    a = ap.parse_args()
    app = create_app()
    with app.app_context():
        since = (datetime.strptime(a.since, "%Y-%m-%d") if a.since
                 else (datetime.utcnow() + timedelta(hours=7) - timedelta(days=3)))
        only = {p.replace("-", "").replace(".", "").replace(" ", "").upper() for p in (a.plate or [])} or None
        out = gps_backfill.fill(app, since, budget_s=a.budget, only=only, dry=a.dry,
                                log=lambda s: print(s, flush=True))
        print("backfill", datetime.utcnow().strftime("%Y-%m-%d %H:%M"), out, flush=True)


if __name__ == "__main__":
    sys.exit(main())
