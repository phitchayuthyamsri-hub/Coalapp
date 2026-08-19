import os
from flask import Flask
from flask_login import LoginManager

from config import Config, gps_providers_config
from .models import db, User

login_manager = LoginManager()
login_manager.login_view = "auth.login"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def create_app(config_class=Config):
    app = Flask(__name__)
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

    with app.app_context():
        db.create_all()
        _ensure_user_schema()
        _ensure_admin()
        _ensure_listrow_schema()
        _ensure_subcontractors()
        _ensure_plan_settings()
        _ensure_shifts()
        from .seed import seed_if_empty
        seed_if_empty()

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

    if Subcontractor.query.first() is None:
        for name, short in SUBCONTRACTORS:
            db.session.add(Subcontractor(name=name, short=short))
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
