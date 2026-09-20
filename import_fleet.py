#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import the Bac Nam fleet list: plates, drivers, phones, and the fixed route.

    python import_fleet.py <file.xlsx>               # say what would change
    python import_fleet.py <file.xlsx> --apply       # do it
    python import_fleet.py <file.xlsx> --no-routes   # plates only, leave routes alone

The workbook is the company's own, kept in Vietnamese, one sheet per revision.
The newest registration sheet is the fleet; the rest are history and are not
read. "Cung co dinh" on each row is the route that truck always runs, named in
Vietnamese - mapped here onto the routes already built on the Route page,
because those are the same three runs by their English names.

Nothing is invented: a truck the sheet does not mention is left exactly as it
is, and a value the sheet leaves blank does not overwrite one already stored.
Run it twice and the second run reports nothing.
"""
import json
import os
import re
import sys

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import create_app                       # noqa: E402
from app.models import db, Truck, Route, KVStore # noqa: E402

# The sheet that is the fleet. The others are earlier revisions of it.
SHEET = "Danh sách đăng ký 16,9"

# Vietnamese fixed route -> the route on the Route page. The English names are
# the ones already built there; the Vietnamese is kept on the route's note so
# the company's own wording is not lost in the mapping.
ROUTE_MAP = {
    "Bốc Mỏ- Trả hàng Chân Mây (đi thẳng không hạ tải)": "Mine : Chan May",
    "Ango- Mỏ- Ango": "Mine : A Ngo",
    "Chạy Bo hàng Ango- Chân Mây": "A Ngo : Chan May",
}

COL = {"plate": 1, "kind": 2, "driver": 3, "phone": 4, "note": 5, "route": 6}

# The fleet page's own tombstone list: plates someone pressed Remove on. It is
# team-wide (the shared key-value store), so it outlives any one browser.
HIDDEN_KEY = "actualGpsFleetHidden_v1"


def norm_plate(s):
    return re.sub(r"[^A-Za-z0-9]", "", str(s or "")).upper()


def phone_digits(s):
    """The number itself, with the ways of writing it stripped off.

    The fleet already holds +84913701780 and the sheet writes 0913701780 -
    and sometimes 0982.409.293. Those are one number in three spellings, so
    comparing the text would report a change that is not one, and applying it
    would trade a clean international number for a dotted local one.
    """
    d = re.sub(r"\D", "", str(s or ""))
    if d.startswith("84") and len(d) > 9:
        d = d[2:]
    return d.lstrip("0")


def clean_phone(s):
    """As written in the sheet, minus the punctuation."""
    return re.sub(r"[^\d+]", "", str(s or ""))


def read_sheet(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[SHEET]
    rows = [[("" if c is None else str(c).strip()) for c in r]
            for r in ws.iter_rows(values_only=True)]
    head = next(i for i, r in enumerate(rows) if r and r[0] == "STT")
    out = []
    for r in rows[head + 1:]:
        if len(r) <= COL["route"] or not r[COL["plate"]]:
            continue
        out.append({k: r[i] for k, i in COL.items()})
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    apply = "--apply" in sys.argv
    # Trucks without their routes. Prod has no A Ngo Warehouse zone, so two of
    # the three runs cannot exist there yet - but the trucks still need to be
    # in the fleet, because the GPS poller only asks for plates it finds in the
    # truck table. Coverage first; the routes can follow the zone.
    no_routes = "--no-routes" in sys.argv
    fleet = read_sheet(path)

    app = create_app()
    with app.app_context():
        routes = {} if no_routes else {r.name: r for r in Route.query.all()}
        missing = [] if no_routes else sorted(
            {v for v in ROUTE_MAP.values() if v not in routes})
        if missing:
            print("These routes are not on the Route page yet, so the trucks that")
            print("run them cannot be pointed at one. Build them first:")
            for m in missing:
                print("   " + m)
            return 1

        trucks = {norm_plate(t.plate): t for t in Truck.query.all()}
        new, updated, unchanged, unmapped = [], [], 0, set()

        for row in fleet:
            key = norm_plate(row["plate"])
            want_route = None if no_routes else ROUTE_MAP.get(row["route"])
            if row["route"] and not no_routes and not want_route:
                unmapped.add(row["route"])
            t = trucks.get(key)
            if t is None:
                new.append((key, row, want_route))
                continue
            changes = []
            if row["driver"] and (t.driver or "") != row["driver"]:
                changes.append(("driver", t.driver or "-", row["driver"]))
            # Only a different NUMBER counts, not a different spelling of it.
            if row["phone"] and phone_digits(t.phone) != phone_digits(row["phone"]):
                changes.append(("phone", t.phone or "-", clean_phone(row["phone"])))
            if want_route:
                have = routes.get(want_route)
                if have is not None and t.route_id != have.id:
                    was = next((n for n, r in routes.items() if r.id == t.route_id), "-")
                    changes.append(("route", was, want_route))
            if changes:
                updated.append((t, row, want_route, changes))
            else:
                unchanged += 1

        print("Fleet sheet: %s" % SHEET)
        if no_routes:
            print("  (--no-routes: plates, drivers and phones only)")
        print("  rows read        : %d" % len(fleet))
        print("  already correct  : %d" % unchanged)
        print("  to add           : %d" % len(new))
        print("  to update        : %d" % len(updated))
        if unmapped:
            print("\n  Fixed routes with no route on the Route page:")
            for u in sorted(unmapped):
                print("     %s" % u)

        if new:
            print("\nNew trucks:")
            for key, row, want in new:
                print("   %-10s %-22s %-12s %s" % (key, row["driver"], row["phone"],
                                                   want or "(no route)"))
        if updated:
            print("\nChanges to trucks already here:")
            for t, row, want, changes in updated:
                for field, was, now in changes:
                    print("   %-10s %-7s %-24s -> %s" % (norm_plate(t.plate), field,
                                                         was[:24], now))

        if not apply:
            print("\nNothing written. Run again with --apply to make these changes.")
            return 0

        wanted = {norm_plate(r["plate"]) for r in fleet}
        for key, row, want in new:
            t = Truck(plate=key, status="online",
                      driver=row["driver"], phone=clean_phone(row["phone"]))
            if want:
                t.route_id = routes[want].id
            db.session.add(t)
        for t, row, want, changes in updated:
            if row["driver"]:
                t.driver = row["driver"]
            if row["phone"] and phone_digits(t.phone) != phone_digits(row["phone"]):
                t.phone = clean_phone(row["phone"])
            if want:
                t.route_id = routes[want].id
        # A plate removed from the fleet page at some point is TOMBSTONED in a
        # team-wide list, and the page hides anything on it - so a truck the
        # sheet puts back would be imported, stored, and then quietly not
        # shown. Importing a plate is saying it is in the fleet, so the
        # tombstone goes with it.
        row = db.session.get(KVStore, HIDDEN_KEY)
        if row:
            try:
                hidden = json.loads(row.value or "[]")
            except ValueError:
                hidden = []
            keep = [h for h in hidden if norm_plate(h) not in wanted]
            if len(keep) != len(hidden):
                row.value = json.dumps(keep)
                print("  un-hid %d plate(s) the fleet page was tombstoning"
                      % (len(hidden) - len(keep)))

        # The company's own wording for each run, kept where the run is.
        for vi, en in ({} if no_routes else ROUTE_MAP).items():
            r = routes.get(en)
            if r is not None and (r.note or "") != vi:
                r.note = vi[:300]
        db.session.commit()
        print("\nDone: %d added, %d updated." % (len(new), len(updated)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
