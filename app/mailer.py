# -*- coding: utf-8 -*-
"""Outgoing email (09/11/2026).

Through the same Google Apps Script relay the Logistics platform uses: the
droplet's SMTP ports are blocked by DigitalOcean, HTTPS is not. The URL and its
secret live in .env only (MAIL_RELAY_URL / MAIL_RELAY_SECRET) and are never
written into the code or a page. Without them nothing is sent and the caller
is told so - mail is a convenience on top of the action, never a condition of
it.
"""
import base64
import json
import os
import urllib.request


def configured():
    return bool(os.environ.get("MAIL_RELAY_URL") and os.environ.get("MAIL_RELAY_SECRET"))


def send_mail(to, subject, html="", text="", cc="", files=None, timeout=45):
    """to / cc: 'a@x, b@y' or a list. files: [(name, bytes, mime)].

    Returns (ok, message) and never raises.
    """
    url = os.environ.get("MAIL_RELAY_URL", "")
    secret = os.environ.get("MAIL_RELAY_SECRET", "")
    if not url or not secret:
        return False, "mail relay not configured"
    j = lambda v: ", ".join(v) if isinstance(v, (list, tuple)) else str(v or "")
    body = {"secret": secret, "to": j(to), "subject": subject or "",
            "text": text or "", "html": html or "",
            "files": [{"name": n, "type": m or "application/octet-stream",
                       "data": base64.b64encode(b).decode()}
                      for n, b, m in (files or [])]}
    if j(cc):
        body["cc"] = j(cc)
    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = r.read().decode("utf-8", "replace").strip()
        return out == "ok", out[:200]
    except Exception as e:                      # noqa: BLE001 - reported, not raised
        return False, str(e)[:200]
