# -*- coding: utf-8 -*-
"""Adding the trip column must not re-derive any row's state (21/11/2026).

Run: python tests/test_trip_column_no_restate.py

The column was first added through the list that also converts every row's
state from its tick - a one-time step from 2026-09 - so the deploy turned
"applied" rows into "approved" and unticked approved rows into "pending".
A database without the column is upgraded here; every state must survive.
"""
import os, sys, sqlite3, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
_tmp = tempfile.mkdtemp()
path = os.path.join(_tmp, "t.db")
os.environ.update(DATABASE_URL="sqlite:///" + path.replace("\\", "/"),
                  SECRET_KEY="test-only-not-a-real-key", COALAPP_ENV="")
from app import create_app                      # noqa: E402
app = create_app()                              # a full, current schema
c = sqlite3.connect(path)
c.execute("insert into daily_list(id,list_date,state) values (1,'2026-09-20','submitted')")
for i, (st, ready) in enumerate([("applied", 1), ("approved", 0), ("denied", 1), ("pending", 1)], 1):
    c.execute("insert into daily_list_row(id,list_id,plate,key,ready,state) values (?,?,?,?,?,?)",
              (i, 1, "P%d" % i, "P%d" % i, ready, st))
c.execute("alter table daily_list_row drop column trip")     # a database from before 21/11
c.commit(); c.close()
app2 = create_app()                             # boots, sees no trip column, adds it
c = sqlite3.connect(path)
got = [r for r in c.execute("select state, trip from daily_list_row order by id")]
want = [("applied", 1), ("approved", 1), ("denied", 1), ("pending", 1)]
print(("  PASS  " if got == want else "  FAIL  ") + "states untouched, trip 1 everywhere"
      + ("" if got == want else "  got %r" % got))
sys.exit(0 if got == want else 1)
