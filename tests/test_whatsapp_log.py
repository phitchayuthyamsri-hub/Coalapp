# -*- coding: utf-8 -*-
"""A WhatsApp button pressed leaves a line in the activity log.

Run: python tests/test_whatsapp_log.py   (PYTHONIOENCODING=utf-8 on Windows)

01/10/2026, "want to check if team use my function or not". Send Plan opens
each driver's plan message in WhatsApp and the Monitor opens a driver's chat;
neither left any trace, so "has anyone ever sent a plan" could only be guessed
from who had the page open. Now each press is one activity line - who, which
truck, which plan day - and the Activity page counts them per person.
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)

_tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL="sqlite:///" + os.path.join(_tmp, "t.db").replace("\\", "/"),
    SECRET_KEY="test-only-not-a-real-key", COALAPP_ENV="")

from app import create_app                                        # noqa: E402
from app import views                                             # noqa: E402
from app.models import db, User, ActivityEvent                    # noqa: E402

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
    ids = {}
    for name, role in (("mon", "monitor"), ("adm", "admin")):
        u = User(username=name, role=role, is_admin=(role == "admin"))
        u.set_password("x" * 12)
        db.session.add(u)
        db.session.flush()
        ids[role] = str(u.id)
    db.session.commit()


def client(role):
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = ids[role]
        s["_fresh"] = True
    return c


mon = client("monitor")
print("a press is recorded")
r = mon.post("/api/event", json={"events": [
    {"action": "whatsapp", "detail": "Send plan 2026-10-02: 20H01471"},
    {"action": "whatsapp", "detail": "Send plan 2026-10-02: Send all started (12 drivers)"},
    {"action": "whatsapp", "detail": "Send plan 2026-10-02: 20H01475 (Send all)"},
    {"action": "whatsapp", "detail": "Driver chat: 20H01381"},
    {"action": "whatsapp", "detail": "Driver chat: 20H01393 (web)"},
    {"action": "telegram", "detail": "not a thing"}]})
check("the server takes the WhatsApp lines and drops the unknown one", r.get_json(), {"ok": True, "n": 5})
with app.app_context():
    rows = ActivityEvent.query.filter_by(action="whatsapp").all()
    check("each is stored under the person who pressed", {x.username for x in rows}, {"mon"})

print("\nthe Activity page counts them per person")
r = client("monitor").get("/api/admin/activity")
check("only an admin may read it", r.status_code, 403)
act = client("admin").get("/api/admin/activity").get_json()
w = act["mon"]["whatsapp"]
check("two plans sent - the Send all press itself is not a message", w["sends"], 2)
check("two driver chats", w["chats"], 2)
check("the last press is dated", bool(w["last"]), True)
check("somebody who never pressed one counts nothing",
      act.get("adm", {"whatsapp": {"sends": 0, "chats": 0}})["whatsapp"]["sends"], 0)

print("\nthe pages send it")
ev = views._EVENTS
check("Send Plan: the truck's own button", "t.closest('.wa-send')" in ev and "'Send plan '+planDay()" in ev, True)
check("Send Plan: Open WhatsApp while stepping through Send all",
      "t.closest('#waOpen')" in ev and "(Send all)" in ev, True)
check("Send Plan: the plan day comes from the page's own picker", "getElementById('sendDateSel')" in ev, True)
tool = open(os.path.join(ROOT, "app", "tool", "index.html"), encoding="utf-8").read()
check("...and the tool still has the things it reads",
      all(x in tool for x in ('class="wa-send" data-plate=', 'id="sendDateSel"', 'id="waOpen"',
                              'id="waTitle"', 'id="sendAllBtn"')), True)
check("no phone number goes into the log", "phone" in ev.split("Send Plan: a driver")[1].split("var sa=")[0]
      .replace("a phone number has no business", ""), False)
monitor = open(os.path.join(ROOT, "app", "templates", "monitor.html"), encoding="utf-8").read()
cell = monitor.split("function phoneCell(r){")[1].split("\n}\n")[0]
check("Monitor: both chat links carry the truck", cell.count("' data-plate=\"' + esc(r.plate) + '\"'"), 2)
check("Monitor: a press on either is reported",
      bool(re.search(r"closest\('a\.wa, a\.waw'\)[\s\S]{0,400}?action: 'whatsapp'[\s\S]{0,120}?'Driver chat: '", monitor)), True)
activity = open(os.path.join(ROOT, "app", "templates", "activity.html"), encoding="utf-8").read()
check("Activity: the action has a name and the summary a place",
      ("whatsapp:'WhatsApp'" in activity, 'id="waSum"' in activity), (True, True))

print("\nthe injected script still parses")
js = re.search(r"<script>(.*)</script>", ev, re.S).group(1)
p = os.path.join(_tmp, "events.js")
open(p, "w", encoding="utf-8").write(js)
r = subprocess.run(["node", "--check", p], capture_output=True, text=True)
check("node accepts it", (r.returncode, r.stderr[:200]), (0, ""))

print("\n%s" % ("ALL PASS" if not FAIL else "%d FAILED" % FAIL))
sys.exit(1 if FAIL else 0)
