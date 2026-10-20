# -*- coding: utf-8 -*-
"""Every database connection runs in WAL mode and waits for a busy writer.

Run: python tests/test_sqlite_wal.py   (PYTHONIOENCODING=utf-8 on Windows)

20/10/2026: Create user on the admin page failed with "database is locked",
one of up to 90 such failures an hour. In SQLite's default journal a write
locks readers out, the minute GPS pull and the five-minute tool sync write all
day, and a request gave up after five seconds.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

_tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL="sqlite:///" + os.path.join(_tmp, "t.db").replace("\\", "/"),
    SECRET_KEY="test-only-not-a-real-key", COALAPP_ENV="")

from sqlalchemy import text                                       # noqa: E402
from app import create_app                                        # noqa: E402
from app.models import db, User                                   # noqa: E402

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(64)
          + ("" if ok else "got %r want %r" % (got, want)))


app = create_app()
with app.app_context():
    check("the database is in WAL mode",
          db.session.execute(text("PRAGMA journal_mode")).scalar().lower(), "wal")
    check("a busy writer is waited for, 30 s",
          db.session.execute(text("PRAGMA busy_timeout")).scalar(), 30000)

    # A reader holding an open transaction no longer stops a writer.
    import sqlite3
    path = os.path.join(_tmp, "t.db")
    reader = sqlite3.connect(path)
    reader.execute("BEGIN")
    reader.execute("SELECT count(*) FROM user").fetchone()
    u = User(username="hieuoi@test", role="subcontractor")
    u.set_password("x" * 12)
    db.session.add(u)
    try:
        db.session.commit()
        ok = True
    except Exception:
        db.session.rollback()
        ok = False
    reader.rollback()
    reader.close()
    check("a user can be created while another connection is reading", ok, True)

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
