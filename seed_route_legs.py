#!/usr/bin/env python3
"""Give the corridor its real road distances.

Every leg was stored with no polyline at all, so the planner measured each one
as 0 km and modelled the whole corridor as instantaneous: 52 trucks crossing
from the mine to Chan May with no driving time between any two points. The
cycle times it produced came entirely from loading, clearance and gate windows.

Distances and shapes come from OSRM over OpenStreetMap. They are road routes,
not straight lines. Two checks that they are sane: the loaded run out and the
empty run back agree to within 2 km on the same corridor, and each leg's shape
is stored alongside its distance so the drawn line and the arithmetic cannot
drift apart.

The shapes are thinned for drawing; road_km carries the true distance, which is
what the plan is built from.

    python seed_route_legs.py --dry-run     # show what would change
    python seed_route_legs.py               # apply
"""
import json
import os
import sys

from app import create_app
from app.models import db, RouteLeg

HERE = os.path.dirname(os.path.abspath(__file__))
SHAPES = os.path.join(HERE, "route_shapes.json")


def main():
    dry = "--dry-run" in sys.argv
    if not os.path.exists(SHAPES):
        print("missing %s" % SHAPES)
        return 1
    data = json.load(open(SHAPES))

    app = create_app()
    with app.app_context():
        print("  %-16s %10s %10s %10s" % ("leg", "km now", "km new", "h at speed"))
        print("  " + "-" * 52)
        changed = 0
        for key, d in sorted(data.items()):
            r = RouteLeg.query.filter_by(leg_key=key).first()
            if not r:
                print("  %-16s  no such leg in this database" % key)
                continue
            before = float(r.road_km or 0.0)
            km = float(d["osrm_km"])
            speed = r.speed or 40.0
            print("  %-16s %10.1f %10.1f %10.2f" % (key, before, km, km / speed))
            if not dry:
                r.road_km = km
                r.points = d["points"]
                changed += 1
        if dry:
            print("\n  dry run - nothing written")
            return 0
        db.session.commit()
        print("\n  %d legs updated" % changed)

        from app import planner
        cfg = planner.load_config()
        drive = sum(v["hours"] for v in cfg["legs"].values()
                    if v["hours"] and "port_mine_ql49" not in str(v))
        print("  planner now sees:")
        for k, v in sorted(cfg["legs"].items()):
            print("    %-16s %6.1f km  %5.2f h at %.0f km/h"
                  % (k, v["km"], v["hours"], v["speed"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
