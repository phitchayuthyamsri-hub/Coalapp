#!/usr/bin/env python3
"""
One-off GPS pull for all enabled providers (or a single one).

Usage (on the server, from /opt/coalapp):
    python gps_pull.py            # pull every enabled provider once
    python gps_pull.py tct        # pull only TCT

Schedule with cron, e.g. every 5 minutes:
    */5 * * * * cd /opt/coalapp && /opt/coalapp/venv/bin/python gps_pull.py >> /var/log/coalapp_gps.log 2>&1

Safe to run repeatedly: ingestion is idempotent (duplicate pings are skipped).
Does nothing unless a provider is enabled and its credentials are set in .env.
"""
import sys

from app import create_app
from app import gps_ingest


def main():
    app = create_app()
    with app.app_context():
        if len(sys.argv) > 1:
            print(gps_ingest.run_provider(app, sys.argv[1].strip().lower()))
        else:
            results = gps_ingest.run_all(app)
            if not results:
                print("no providers enabled")
            for r in results:
                print(r)


if __name__ == "__main__":
    main()
