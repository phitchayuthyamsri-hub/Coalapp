#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fill in each truck's GPS company from where its positions actually came.

    python fill_gps_provider.py            # say what would change
    python fill_gps_provider.py --apply    # do it

Every ping carries the provider that answered for it (GpsPing.source is
"api:tct", "api:viettel", ...), so a truck's GPS company is not a guess: it is
whoever has been reporting that truck. The most RECENT source wins, because a
truck can move between providers and the old one keeps its history.

A truck with no pings is left blank. Blank is honest - filling it from the
provider's configured plate list would say "Viettel" for a truck Viettel has
never actually answered for, and that is what leaves the fleet page looking
complete while being wrong.

Only blanks are filled by default. A value someone typed is theirs; --overwrite
replaces it when the pings disagree.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import create_app                     # noqa: E402
from app import engine                         # noqa: E402
from app.models import db, GpsPing, Truck      # noqa: E402

# How the provider keys are written on the fleet page.
LABEL = {"tct": "TCT", "tct2": "TCT", "viettel": "Viettel", "adsun": "Adsun"}


def provider_of(source):
    key = (source or "").split(":", 1)[-1].strip().lower()
    return LABEL.get(key, key.upper() if key else "")


def main():
    apply = "--apply" in sys.argv
    overwrite = "--overwrite" in sys.argv
    app = create_app()
    with app.app_context():
        # The newest ping per plate, and the source that delivered it.
        from sqlalchemy import func
        sub = (db.session.query(GpsPing.plate, func.max(GpsPing.dt).label("mx"))
               .group_by(GpsPing.plate).subquery())
        latest = {}
        for plate, src in (db.session.query(GpsPing.plate, GpsPing.source)
                           .join(sub, (GpsPing.plate == sub.c.plate)
                                 & (GpsPing.dt == sub.c.mx)).all()):
            latest[engine.norm_plate(plate)] = provider_of(src)

        fill, differ, no_pings, already = [], [], [], 0
        for t in Truck.query.order_by(Truck.plate).all():
            want = latest.get(engine.norm_plate(t.plate), "")
            have = (t.gps_provider or "").strip()
            if not want:
                no_pings.append(t.plate)
            elif not have:
                fill.append((t, want))
            elif have.lower() != want.lower():
                differ.append((t, have, want))
            else:
                already += 1

        print("  already right      : %d" % already)
        print("  blank, can fill    : %d" % len(fill))
        print("  set but disagreeing: %d" % len(differ))
        print("  no pings, left as is: %d" % len(no_pings))
        if fill:
            print("\nFill:")
            for t, want in fill:
                print("   %-10s -> %s" % (t.plate, want))
        if differ:
            print("\nDisagreeing with the pings%s:"
                  % ("" if overwrite else " (left alone; --overwrite to change)"))
            for t, have, want in differ:
                print("   %-10s stored %-10s pings say %s" % (t.plate, have, want))
        if no_pings:
            print("\nNo pings, so nothing to go on: %s" % ", ".join(no_pings))

        if not apply:
            print("\nNothing written. Run again with --apply.")
            return 0
        for t, want in fill:
            t.gps_provider = want
        if overwrite:
            for t, have, want in differ:
                t.gps_provider = want
        db.session.commit()
        print("\nDone: %d filled%s." % (len(fill),
              (", %d overwritten" % len(differ)) if overwrite else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
