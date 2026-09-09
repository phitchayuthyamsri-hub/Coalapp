#!/usr/bin/env python3
"""
One-off GPS pull for all enabled providers (or a single one).

Usage (on the server, from /opt/coalapp):
    python gps_pull.py            # pull every enabled provider once
    python gps_pull.py tct        # pull only TCT

    python gps_pull.py --all      # ignore the pacing, ask for every truck

Run it every 5 MINUTES. It decides for itself which trucks to ask about:

    inside a set-up polygon   every  5 minutes
    anywhere else             every 30 minutes

so the five-minute schedule is the fast lane, not the rate for everything. A
truck loading at the mine or queueing at the port is measured closely enough to
detect the visit; one driving the corridor between them is asked about a sixth
as often, because its position ages slowly and the road is known.

    */5 * * * * cd /opt/coalapp && /opt/coalapp/venv/bin/python gps_pull.py >> /var/log/coalapp_gps.log 2>&1

One consequence worth knowing: a truck outside a polygon can be up to thirty
minutes inside one before the next pull notices and speeds it up. Entering is
therefore seen late by design; leaving is seen promptly.

Safe to run repeatedly: ingestion is idempotent (duplicate pings are skipped).
Does nothing unless a provider is enabled and its credentials are set in .env.
"""
import sys

from app import create_app
from app import gps_ingest


def main():
    app = create_app()
    with app.app_context():
        args = [a.strip().lower() for a in sys.argv[1:]]
        paced = "--all" not in args
        rest = [a for a in args if not a.startswith("-")]
        if rest:
            # A named provider is a deliberate, manual pull: ask for everything.
            print(gps_ingest.run_provider(app, rest[0]))
        else:
            results = gps_ingest.run_all(app, paced=paced)
            if not results:
                print("no providers enabled")
            for r in results:
                print(r)


if __name__ == "__main__":
    main()
