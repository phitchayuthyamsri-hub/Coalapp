import os
from flask import Flask
from flask_login import LoginManager

from config import Config
from .models import db, User

login_manager = LoginManager()
login_manager.login_view = "auth.login"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)

    from .auth import bp as auth_bp
    from .views import bp as views_bp
    from .api import bp as api_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp)

    @app.before_request
    def _make_session_permanent():
        from flask import session
        session.permanent = True

    with app.app_context():
        db.create_all()
        _ensure_user_schema()
        _ensure_admin()
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
    for st in stmts:
        db.session.execute(text(st))
    if stmts:
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
