import os
from flask import Flask
from flask_login import LoginManager

from config import Config, DEFAULT_SECRET, gps_providers_config, is_staging
from .models import db, User

login_manager = LoginManager()
login_manager.login_view = "auth.login"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@login_manager.unauthorized_handler
def _unauthorized():
    """API calls are made by scripts, not people: answer 401 instead of
    redirecting them into the login flow, where their URL would be remembered
    as the after-login destination and served to a browser as a GET."""
    from flask import request, redirect, jsonify
    from flask_login import login_url
    if request.path == "/api" or request.path.startswith("/api/"):
        return jsonify(error="login required"), 401
    return redirect(login_url(login_manager.login_view, request.url))


def create_app(config_class=Config):
    app = Flask(__name__)
    # The grid is served from /static. With Flask's default twelve-hour cache a
    # corrected grid.js reached nobody until their browser felt like asking
    # again - which looked exactly like the fix not working. Revalidate every
    # time; these files are small and answer 304 when unchanged.
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    @app.context_processor
    def _asset_version():
        """Stamp static URLs with the file's own mtime.

        no-cache tells a browser to revalidate, but a copy taken BEFORE that
        header existed carries no instruction at all and is simply kept - which
        is how a page ended up calling a function that had shipped hours
        earlier. A changed file is now a changed URL, which nothing can hold on
        to by mistake.
        """
        import os as _os

        def asset_v(name):
            try:
                return str(int(_os.path.getmtime(
                    _os.path.join(app.static_folder, name))))
            except OSError:
                return "0"
        return {"asset_v": asset_v}
    app.config.from_object(config_class)

    # GPS ingestion config (inert unless a provider is enabled + credentialed).
    try:
        app.config["_GPS_CFG"] = gps_providers_config()
    except Exception:
        app.config["_GPS_CFG"] = {}

    db.init_app(app)
    login_manager.init_app(app)

    from .auth import bp as auth_bp
    from .views import bp as views_bp
    from .api import bp as api_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp)
    from .tool_link import bp as tool_link_bp
    app.register_blueprint(tool_link_bp)

    # GPS capture routes — isolated; a fault here must never break the main app.
    try:
        from .gps_routes import bp as gps_bp
        app.register_blueprint(gps_bp)
    except Exception as e:  # pragma: no cover
        app.logger.warning("GPS routes not loaded: %s", e)

    # WI LA-NT-001 routes (return route + windows) — likewise isolated.
    try:
        from .wi_routes import bp as wi_bp
        app.register_blueprint(wi_bp)
    except Exception as e:  # pragma: no cover
        app.logger.warning("WI routes not loaded: %s", e)

    # Shift Board (monitoring agendas) — isolated for the same reason.
    try:
        from .shift_routes import bp as shift_bp, page_bp as shift_page_bp
        app.register_blueprint(shift_bp)
        app.register_blueprint(shift_page_bp)
    except Exception as e:  # pragma: no cover
        app.logger.warning("Shift routes not loaded: %s", e)

    @app.before_request
    def _make_session_permanent():
        from flask import session
        session.permanent = True

    # A login is only as good as the key it is signed with. On the shipped
    # default, anyone who has read the source can mint a session cookie for
    # this box - and nothing said so, which is how the sandbox ran that way
    # for days. Say it at every boot, where the logs will carry it.
    if app.config.get("SECRET_KEY") == DEFAULT_SECRET:
        app.logger.warning(
            "SECRET_KEY is the shipped default - sessions can be forged. "
            "Set SECRET_KEY in the systemd unit for this instance.")

    # Templates ask whether this is the sandbox when a change is being tried
    # out before the real day sees it, so the answer lives in one place.
    _staging = is_staging()
    app.config["STAGING"] = _staging
    app.jinja_env.globals["STAGING"] = _staging

    # The sandbox announces itself on every page - same orange banner idea as
    # the logistics program - so nobody mistakes test data for the real day.
    if _staging:
        _BANNER = (b'<div style="position:sticky;top:0;z-index:99999;'
                   b'background:#b45309;color:#fff;text-align:center;'
                   b'font:700 12px/1.6 sans-serif;letter-spacing:.5px;'
                   b'padding:3px 8px">STAGING &mdash; a sandbox with its own '
                   b'data. Nothing here reaches the real day.</div>')

        @app.after_request
        def _staging_banner(resp):
            try:
                if (resp.content_type or "").startswith("text/html") \
                        and not resp.direct_passthrough:
                    body = resp.get_data()
                    i = body.find(b"<body")
                    if i >= 0:
                        j = body.find(b">", i)
                        if j >= 0:
                            resp.set_data(body[:j + 1] + _BANNER + body[j + 1:])
            except Exception:
                pass
            return resp

    with app.app_context():
        # Several gunicorn workers boot at the same instant and each runs this.
        # create_all checks first and creates second, so two of them can both
        # find a new table missing and one then fails on "already exists" -
        # which happened to a worker the first time anchor_version shipped.
        # The loser simply asks again: by then the table is there.
        _create_all_racing()
        _ensure_user_schema()
        _ensure_admin()
        _ensure_listrow_schema()
        _ensure_daily_list_schema()
        _ensure_truck_schema()
        _ensure_subcontractors()
        _ensure_plan_settings()
        _ensure_routeleg_schema()
        _ensure_anchor_schema()
        _ensure_snapshot_schema()
        _ensure_shifts()
        from .seed import seed_if_empty
        seed_if_empty()
        # After seeding, not only before: on a fresh database the zones do not
        # exist yet when the schema step runs, and a zone with no "since the
        # beginning" version would be judged as never having existed before
        # its first edit - the exact loss versioning is there to prevent.
        from .geofence import ensure_versions
        ensure_versions()

    return app


def _ensure_user_schema():
    """Add is_admin / allowed_tabs columns to an existing user table if missing."""
    from sqlalchemy import inspect, text
    insp = inspect(db.engine)
    try:
        cols = [c["name"] for c in insp.get_columns("user")]
    except Exception:
        return
    stmts = []
    if "is_admin" not in cols:
        stmts.append('ALTER TABLE "user" ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0')
    if "allowed_tabs" not in cols:
        stmts.append('ALTER TABLE "user" ADD COLUMN allowed_tabs TEXT')
    if "lang" not in cols:
        stmts.append('ALTER TABLE "user" ADD COLUMN lang VARCHAR(2) DEFAULT \'en\'')
    if "default_page" not in cols:
        stmts.append('ALTER TABLE "user" ADD COLUMN default_page VARCHAR(20)')
    if "can_edit" not in cols:
        stmts.append('ALTER TABLE "user" ADD COLUMN can_edit BOOLEAN NOT NULL DEFAULT 1')
    if "allowed_apps" not in cols:
        stmts.append('ALTER TABLE "user" ADD COLUMN allowed_apps TEXT')
    if "subcontractor_id" not in cols:
        stmts.append('ALTER TABLE "user" ADD COLUMN subcontractor_id INTEGER')
    if "alerts_seen_at" not in cols:
        stmts.append('ALTER TABLE "user" ADD COLUMN alerts_seen_at DATETIME')
    if "allowed_views" not in cols:
        stmts.append('ALTER TABLE "user" ADD COLUMN allowed_views TEXT')
    added_role = "role" not in cols
    if added_role:
        stmts.append('ALTER TABLE "user" ADD COLUMN role VARCHAR(20) DEFAULT \'monitor\'')
    for st in stmts:
        db.session.execute(text(st))
    if stmts:
        db.session.commit()
    if added_role:
        # One-time backfill on the migration pass only. The new column defaults
        # every existing row to 'monitor', so map the current admins across
        # before anyone loses the access they already had.
        db.session.execute(text('UPDATE "user" SET role=\'admin\' WHERE is_admin=1'))
        db.session.commit()


SUBCONTRACTORS = [
    # Bac Nam Transport carries the project fleet - the 50 trucks the corridor
    # is planned around. Listed first because it is the company the day is built
    # on, not one of the occasional hauliers below it.
    ("Bac Nam", "Bac Nam"),
    ("PTS", "PTS"), ("Hoanh Son", "Hoanh Son"), ("Bao Binh", "BBC"),
    ("Alpha", "Alpha"), ("Nam Tien (Dong Bac)", "Nam Tien"), ("DTT", "DTT"),
    ("An Viet", "An Viet"), ("Vinh Phu", "Vinh Phu"), ("Duy Linh", "Duy Linh"),
    ("KCL", "KCL"), ("MHC", "MHC"), ("No data", "No data"),
]


def _ensure_subcontractors():
    """Seed the companies, and widen daily_list to one list per company per day."""
    from sqlalchemy import inspect, text
    from .models import Subcontractor
    insp = inspect(db.engine)

    # daily_list.subcontractor_id, and drop the old one-list-per-date rule
    try:
        dcols = [c["name"] for c in insp.get_columns("daily_list")]
        if "subcontractor_id" not in dcols:
            db.session.execute(text(
                "ALTER TABLE daily_list ADD COLUMN subcontractor_id INTEGER"))
            db.session.commit()
        for ix in insp.get_indexes("daily_list"):
            if ix.get("unique") and ix.get("column_names") == ["list_date"]:
                db.session.execute(text("DROP INDEX IF EXISTS %s" % ix["name"]))
                db.session.commit()
        db.session.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_daily_list "
            "ON daily_list (list_date, subcontractor_id)"))
        db.session.commit()
    except Exception as e:  # pragma: no cover
        db.session.rollback()

    # Top up per company rather than all-or-nothing: a database seeded before a
    # haulier joined the project would otherwise never receive it, and the
    # company would be missing from every picker with no way to add it.
    added = 0
    for name, short in SUBCONTRACTORS:
        if Subcontractor.query.filter_by(name=name).first():
            continue
        db.session.add(Subcontractor(name=name, short=short))
        added += 1
    if added:
        db.session.commit()


PLAN_DEFAULTS = [
    # key, value, label, unit, group, order
    ("load_hours",        "1.0",   "Mine turnaround per truck",          "hours", "mine",   10),
    ("mine_bays",         "2",     "Loading bays at the mine",           "bays",  "mine",   11),
    ("mine_247",          "yes",   "Mine loads around the clock",        "yes/no", "mine",  12),
    ("turn_gap_hours",    "0",     "Rest at the mine before turning again", "hours", "mine", 13),
    ("clearance_hours",   "3.0",   "Border clearance (paperwork)",       "hours", "border", 20),
    ("unload_hours",      "0.5",   "Port turnaround per truck",          "hours", "port",   30),
    ("port_bays",         "1",     "Unloading bays at the port",         "bays",  "port",   34),
    ("border_open",       "15:00", "Lalay border, loaded - opens",       "time",  "border", 21),
    ("border_close",      "19:00", "Lalay border, loaded - closes",      "time",  "border", 22),
    ("ql49_in_open",      "19:00", "QL49 loaded inbound - opens",        "time",  "ql49",   40),
    ("ql49_in_close",     "24:00", "QL49 loaded inbound - closes",       "time",  "ql49",   41),
    ("port_open",         "07:00", "Port unloading - opens",             "time",  "port",   31),
    ("port_close",        "17:00", "Port unloading - closes",            "time",  "port",   32),
    ("ql49_out_open",     "00:00", "QL49 empty outbound - opens",        "time",  "ql49",   42),
    ("ql49_out_close",    "05:00", "QL49 empty outbound - closes",       "time",  "ql49",   43),
    ("border_out_open",   "07:00", "Lalay border, empty - opens",        "time",  "border", 23),
    ("border_out_close",  "19:00", "Lalay border, empty - closes",       "time",  "border", 24),
    ("backhaul_cutoff",   "14:00", "Unload finished by this = Hue route", "time", "port",   33),
]


def _ensure_plan_settings():
    """Seed the planner's tunables once. They are data on purpose - every one of
    them is an estimate that the operation will correct."""
    from .models import PlanSetting
    # Top up per key rather than all-or-nothing: a database seeded before a new
    # tunable existed would otherwise never receive it, and the planner would
    # silently fall back to a hard-coded default nobody can see or change.
    added = 0
    for key, val, label, unit, group, order in PLAN_DEFAULTS:
        if db.session.get(PlanSetting, key):
            continue
        db.session.add(PlanSetting(key=key, value=val, label=label,
                                   unit=unit, group=group, ordering=order))
        added += 1
    if added:
        db.session.commit()

def _ensure_routeleg_schema():
    """Add RouteLeg.road_km to a database created before the column existed."""
    from sqlalchemy import inspect, text
    insp = inspect(db.engine)
    try:
        cols = [c["name"] for c in insp.get_columns("route_leg")]
    except Exception:
        return
    if "road_km" not in cols:
        db.session.execute(text("ALTER TABLE route_leg ADD COLUMN road_km FLOAT"))
        db.session.commit()


def _ensure_snapshot_schema():
    """Add PlanSnapshot.day to a database created before day revisions existed."""
    from sqlalchemy import inspect, text
    insp = inspect(db.engine)
    try:
        cols = [c["name"] for c in insp.get_columns("plan_snapshot")]
    except Exception:
        return
    if "day" not in cols:
        db.session.execute(text("ALTER TABLE plan_snapshot ADD COLUMN day VARCHAR(10)"))
        db.session.commit()


def _create_all_racing():
    from sqlalchemy.exc import OperationalError
    for attempt in range(3):
        try:
            db.create_all()
            return
        except OperationalError as e:
            if "already exists" not in str(e) or attempt == 2:
                raise
            db.session.rollback()


def _add_column_racing(table, column_sql):
    """ALTER TABLE ... ADD COLUMN, tolerant of another worker having just done
    it. SQLite says "duplicate column name"; that means it is there."""
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    try:
        db.session.execute(text("ALTER TABLE %s ADD COLUMN %s" % (table, column_sql)))
        db.session.commit()
    except OperationalError as e:
        db.session.rollback()
        if "duplicate column" not in str(e).lower():
            raise


def _ensure_anchor_schema():
    """Geofences became versioned on 18/09/2026: two columns on Anchor, and a
    first "since the beginning" version for every zone that has none - so the
    shape already in the table is what history keeps being judged by."""
    from sqlalchemy import inspect, text
    insp = inspect(db.engine)
    try:
        cols = [c["name"] for c in insp.get_columns("anchor")]
    except Exception:
        return
    if "caption" not in cols:
        _add_column_racing("anchor", "caption VARCHAR(60) DEFAULT ''")
    if "retired_at" not in cols:
        _add_column_racing("anchor", "retired_at DATETIME")
    # The place's working conditions (20/09/2026). Blank and NULL are the
    # honest defaults: an existing zone has not been told any of this yet, and
    # "not recorded" must not read as "zero bays" or "midnight to midnight".
    if "loc_type" not in cols:
        _add_column_racing("anchor", "loc_type VARCHAR(20) DEFAULT ''")
    if "window_open" not in cols:
        _add_column_racing("anchor", "window_open VARCHAR(5) DEFAULT ''")
    if "window_close" not in cols:
        _add_column_racing("anchor", "window_close VARCHAR(5) DEFAULT ''")
    if "loading_bays" not in cols:
        _add_column_racing("anchor", "loading_bays INTEGER")
    if "loading_time_min" not in cols:
        _add_column_racing("anchor", "loading_time_min INTEGER")
    from .geofence import ensure_versions
    try:
        ensure_versions()
    except Exception:
        # Two workers backfilling at once: one commits, the other's insert
        # can collide. Whoever lost rolls back; the rows are there.
        db.session.rollback()


def _ensure_truck_schema():
    """Add the Truck columns that arrived after the table first shipped."""
    from sqlalchemy import inspect, text
    insp = inspect(db.engine)
    try:
        cols = [c["name"] for c in insp.get_columns("truck")]
    except Exception:
        return
    if "driver" not in cols:
        db.session.execute(text("ALTER TABLE truck ADD COLUMN driver VARCHAR(120) DEFAULT ''"))
        db.session.commit()
    if "gps_last_pull" not in cols:
        db.session.execute(text("ALTER TABLE truck ADD COLUMN gps_last_pull DATETIME"))
        db.session.commit()
    if "route_id" not in cols:
        _add_column_racing("truck", "route_id INTEGER")


def _ensure_daily_list_schema():
    """Add the amend-request columns to an existing daily_list."""
    from sqlalchemy import inspect, text
    insp = inspect(db.engine)
    try:
        cols = [c["name"] for c in insp.get_columns("daily_list")]
    except Exception:
        return
    want = [("content_hash", "VARCHAR(40)"),
            ("amend_state", "VARCHAR(10) DEFAULT ''"),
            ("amend_by", "VARCHAR(80) DEFAULT ''"),
            ("amend_at", "DATETIME"),
            ("amend_note", "VARCHAR(300) DEFAULT ''"),
            ("amend_by_role", "VARCHAR(20) DEFAULT ''"),
            ("amend_decided_by", "VARCHAR(80) DEFAULT ''"),
            ("amend_decided_at", "DATETIME"),
            ("amend_reason", "VARCHAR(300) DEFAULT ''"),
            ("date_basis", "VARCHAR(8) DEFAULT ''")]
    stmts = ["ALTER TABLE daily_list ADD COLUMN %s %s" % (n, t)
             for n, t in want if n not in cols]
    for st in stmts:
        # Three gunicorn workers start together and all run this; the ones that
        # lose the race find the column already there, which is not an error.
        try:
            db.session.execute(text(st))
            db.session.commit()
        except Exception:
            db.session.rollback()
    _move_sheet_dates_to_use_day()


def _move_sheet_dates_to_use_day():
    """Re-date sheets filed before a sheet's date meant the day it is USED.

    They carry the day they were sent - the day before their trucks run - so
    each moves forward one day, once. Every worker reaches this at the same
    moment, so it is two single statements in one transaction rather than a
    read and a write: park the unconverted sheets under a marked date (which
    cannot collide with a real one, so the per-company unique rule holds
    mid-way), then give each its new date and stamp it. Whoever runs second
    finds nothing left to move.
    """
    from sqlalchemy import text
    try:
        db.session.execute(text(
            "UPDATE daily_list SET list_date = '~' || date(list_date, '+1 day'), "
            "date_basis = 'moving' WHERE COALESCE(date_basis, '') = ''"))
        db.session.execute(text(
            "UPDATE daily_list SET list_date = substr(list_date, 2), "
            "date_basis = 'use' WHERE date_basis = 'moving'"))
        db.session.commit()
    except Exception:
        db.session.rollback()


def _ensure_listrow_schema():
    """Add the per-row state / arrival columns to an existing daily_list_row."""
    from sqlalchemy import inspect, text
    insp = inspect(db.engine)
    try:
        cols = [c["name"] for c in insp.get_columns("daily_list_row")]
    except Exception:
        return
    stmts = []
    if "state" not in cols:
        stmts.append("ALTER TABLE daily_list_row ADD COLUMN state VARCHAR(10) DEFAULT 'pending'")
    if "arrive_hhmm" not in cols:
        stmts.append("ALTER TABLE daily_list_row ADD COLUMN arrive_hhmm VARCHAR(5) DEFAULT ''")
    if "back_in_service" not in cols:
        stmts.append("ALTER TABLE daily_list_row ADD COLUMN back_in_service VARCHAR(10) DEFAULT ''")
    if "remark" not in cols:
        stmts.append("ALTER TABLE daily_list_row ADD COLUMN remark VARCHAR(300) DEFAULT ''")
    if "arrive_date" not in cols:
        stmts.append("ALTER TABLE daily_list_row ADD COLUMN arrive_date VARCHAR(10) DEFAULT ''")
    if "location" not in cols:
        stmts.append("ALTER TABLE daily_list_row ADD COLUMN location VARCHAR(60) DEFAULT ''")
    if "sheet_status" not in cols:
        stmts.append("ALTER TABLE daily_list_row ADD COLUMN sheet_status VARCHAR(30) DEFAULT ''")
    for st in stmts:
        db.session.execute(text(st))
    if stmts:
        db.session.commit()
        # Existing rows predate per-row state: a ticked truck was already going.
        db.session.execute(text(
            "UPDATE daily_list_row SET state='sent' WHERE ready=1"))
        db.session.execute(text(
            "UPDATE daily_list_row SET state='pending' WHERE ready=0"))
        db.session.commit()
    # 'sent'/'rejected' were the old words for the same decision.
    db.session.execute(text("UPDATE daily_list_row SET state='approved' WHERE state='sent'"))
    db.session.execute(text("UPDATE daily_list_row SET state='denied' WHERE state='rejected'"))
    db.session.commit()


def _ensure_shifts():
    """Seed the three default shifts once. Shifts are data - editing or deleting
    them here is expected, so this only ever runs on an empty table."""
    from .models import Shift, ShiftCheck
    if Shift.query.first():
        return
    plan = [
        ("Morning", "06:00", "14:00", [
            ("arrive_mine", "Truck arrived at XPPL Mine (fronthaul)"),
            ("unload_done", "Truck finished unloading at Chan May Port"),
        ]),
        ("Afternoon", "14:00", "22:00", [
            ("depart_border", "Truck departed Lalay border"),
        ]),
        ("Night", "22:00", "06:00", [
            ("depart_ql49", "Truck departed QL49"),
        ]),
    ]
    for i, (name, start, end, checks) in enumerate(plan):
        s = Shift(name=name, start_hhmm=start, end_hhmm=end, ordering=i, active=True)
        db.session.add(s)
        db.session.flush()
        for j, (code, label) in enumerate(checks):
            db.session.add(ShiftCheck(shift_id=s.id, code=code, label=label, ordering=j))
    db.session.commit()


def _ensure_admin():
    """Pin the owner account as admin; fall back to earliest user if absent."""
    from sqlalchemy import func
    name = os.environ.get("ADMIN_USERNAME", "PhitchayuthYamsri")
    if name:
        owner = User.query.filter(func.lower(User.username) == name.lower()).first()
        if owner and not owner.is_admin:
            owner.is_admin = True
            db.session.commit()
    if User.query.filter_by(is_admin=True).first():
        return
    first = User.query.order_by(User.id.asc()).first()
    if first:
        first.is_admin = True
        db.session.commit()
