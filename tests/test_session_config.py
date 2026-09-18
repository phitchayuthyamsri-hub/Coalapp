# -*- coding: utf-8 -*-
"""Why people kept being asked to log in again.

Run: python tests/test_session_config.py

Two faults, compounding, both on the same droplet:

  A browser scopes a cookie by HOST and ignores the port. Prod on :8080 and the
  staging sandbox on :8082 are therefore one cookie jar, and both were setting
  a cookie called "coalapp_session". Each login overwrote the other's - and
  because the two sign with different keys, the overwritten cookie was not
  merely replaced, it was unreadable. Every switch between the two open tabs
  was a fresh login.

  The session then lasted thirty minutes of idling, which signed people out in
  the middle of a working day.
"""
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

FAIL = 0


def check(label, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("  PASS  " if ok else "  FAIL  ") + label.ljust(58)
          + ("" if ok else "got %r want %r" % (got, want)))


def under(env, fn):
    """Call fn(config module) with exactly this environment in place.

    The value has to be TAKEN inside the context: Config's attributes are fixed
    when the class body runs, but is_staging() reads the environment when it is
    called, and a helper that restores the environment before returning would
    be asking the wrong question.
    """
    keys = ("COALAPP_ENV", "SESSION_HOURS", "SECRET_KEY")
    saved = {k: os.environ.get(k) for k in keys}
    try:
        for k in keys:
            os.environ.pop(k, None)
        for k, v in env.items():
            os.environ[k] = v
        sys.modules.pop("config", None)
        return fn(importlib.import_module("config"))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sys.modules.pop("config", None)


def cfg(**env):
    """config.Config as it would be under this environment."""
    return under(env, lambda m: m.Config)


def staging_under(**env):
    return under(env, lambda m: m.is_staging())


def const_under(name, **env):
    return under(env, lambda m: getattr(m, name))


print("the two instances must not share a cookie")
prod = cfg()
stg = cfg(COALAPP_ENV="staging")
check("prod's cookie name", prod.SESSION_COOKIE_NAME, "coalapp_session")
check("staging's cookie name", stg.SESSION_COOKIE_NAME, "coalapp_staging_session")
check("they differ - the whole point",
      prod.SESSION_COOKIE_NAME != stg.SESSION_COOKIE_NAME, True)
check("neither is the bare Flask default",
      "session" in (prod.SESSION_COOKIE_NAME, stg.SESSION_COOKIE_NAME), False)
check("...so the logistics app on this box is untouched too",
      prod.SESSION_COOKIE_NAME.startswith("coalapp"), True)

print("\nis_staging is the single definition")
check("unset means prod", staging_under(), False)
check("'staging' means staging", staging_under(COALAPP_ENV="staging"), True)
check("case and spacing are forgiven", staging_under(COALAPP_ENV=" STAGING "), True)
check("anything else is prod", staging_under(COALAPP_ENV="prod"), False)

print("\na session lasts a shift, not half an hour")
base = cfg()
check("the default is 12 hours",
      base.PERMANENT_SESSION_LIFETIME.total_seconds() / 3600, 12.0)
check("it is a sliding window", base.SESSION_REFRESH_EACH_REQUEST, True)
check("...and no shorter than it used to be",
      base.PERMANENT_SESSION_LIFETIME.total_seconds() > 30 * 60, True)
check("SESSION_HOURS overrides it",
      cfg(SESSION_HOURS="8").PERMANENT_SESSION_LIFETIME.total_seconds() / 3600, 8.0)
# A typo in a unit file must not stop the app booting.
for bad in ("", "abc", "0", "-3", "  "):
    check("SESSION_HOURS=%-5r falls back to 12" % bad,
          cfg(SESSION_HOURS=bad).PERMANENT_SESSION_LIFETIME.total_seconds() / 3600,
          12.0)

print("\nthe default signing key is named, so it cannot hide")
check("the default is a known constant", const_under("DEFAULT_SECRET"), "change-me-in-production")
check("an unset SECRET_KEY lands on it", cfg().SECRET_KEY, "change-me-in-production")
check("a set one is used", cfg(SECRET_KEY="realkey").SECRET_KEY, "realkey")

print("\n  %d FAILING" % FAIL if FAIL else "\n  all pass")
sys.exit(1 if FAIL else 0)
