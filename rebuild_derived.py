#!/usr/bin/env python3
"""Build the derived visit/cycle layer, or check it against the live path.

Usage (on the server, from /opt/coalapp or /opt/coalapp-staging):

    python rebuild_derived.py            # wipe and rebuild from every ping
    python rebuild_derived.py --check    # compare stored against live, no write

Nothing in the app reads these tables yet - this is the step that proves the
derived layer matches what the pages compute today. A rebuild is safe to run
at any time: it only ever touches the two derived tables, never the pings.
"""

import sys

from app import create_app
from app.derive import rebuild, check

app = create_app()

with app.app_context():
    if "--check" in sys.argv:
        r = check()
        print("live   : %d visits, %d cycles" % (r["live_visits"], r["live_cycles"]))
        print("stored : %d visits, %d cycles" % (r["stored_visits"], r["stored_cycles"]))
        print("differences: %d" % r["differences"])
        for what, key in r["first"]:
            print("   %-24s %s" % (what, key))
        sys.exit(1 if r["differences"] else 0)

    r = rebuild()
    print("rebuilt: %d visits (%d frozen), %d cycles (%d frozen)"
          % (r["visits"], r["visits_frozen"], r["cycles"], r["cycles_frozen"]))
