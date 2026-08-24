from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, session, abort)
from flask_login import login_user, logout_user, login_required, current_user

from .models import db, User, Subcontractor
from . import activity

bp = Blueprint("auth", __name__)


def _sub_id_for(role, raw):
    """Which company a login is scoped to.

    Only a subcontractor login carries one, and it must name a real company:
    an unscoped subcontractor account would fall through to the legacy list
    instead of being confined to its own trucks, which is the opposite of the
    point. Every other role carries none - an id left on a monitor is dead data
    that reads like a restriction.
    """
    if role != "subcontractor":
        return None
    try:
        sid = int(raw)
    except (TypeError, ValueError):
        return None
    return sid if db.session.get(Subcontractor, sid) else None


@bp.route("/register", methods=["GET", "POST"])
def register():
    """Create an account. Admins only.

    Accounts used to be open to anyone who could reach the server, which on a
    public address means anyone at all - and a new account defaults to seeing
    every company's trucks, drivers and GPS trails. The one exception is an
    empty system: somebody has to be able to make the first account, and there
    is no admin yet to authorise it.
    """
    from .api import ROLE_KEYS
    bootstrap = (User.query.count() == 0)
    if not bootstrap:
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.path))
        if not getattr(current_user, "is_admin", False):
            abort(403)

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if not username or not password:
            flash("Username and password required.")
            return redirect(url_for("auth.register"))
        if User.query.filter(db.func.lower(User.username) == username.lower()).first():
            flash("That username is taken.")
            return redirect(url_for("auth.register"))

        role = (request.form.get("role") or "monitor").strip().lower()
        if role not in ROLE_KEYS:
            role = "monitor"
        sub_id = _sub_id_for(role, request.form.get("subcontractor_id"))
        if role == "subcontractor" and sub_id is None:
            flash("Choose which company this subcontractor login belongs to.")
            return redirect(url_for("auth.register"))

        u = User(username=username)
        u.set_password(password)
        u.role = "admin" if bootstrap else role
        u.subcontractor_id = sub_id
        if bootstrap:
            u.is_admin = True
        db.session.add(u)
        db.session.commit()

        # An admin creating an account stays signed in as themselves. Logging in
        # as the new user would silently swap the session out from under them.
        if bootstrap:
            login_user(u)
            session.permanent = True
            return redirect(url_for("views.dashboard"))
        flash("Created %s (%s)." % (u.username, u.role))
        return redirect(url_for("views.admin"))

    subs = Subcontractor.query.filter_by(active=True).order_by(
        Subcontractor.name).all() if not bootstrap else []
    return render_template("register.html", bootstrap=bootstrap,
                           roles=ROLE_KEYS, subs=subs)


def _safe_next(target):
    """Only allow same-site relative paths (e.g. "/gps-capture"); reject absolute
    URLs and protocol-relative "//host" to avoid open-redirects. API paths are
    rejected too: they are fetch targets, not pages — a background tracker
    bounced through login must never become the after-login destination."""
    if not target:
        return None
    if target.startswith("/") and not target.startswith("//") and "\\" not in target:
        if target == "/api" or target.startswith("/api/"):
            return None
        return target
    return None


@bp.route("/login", methods=["GET", "POST"])
def login():
    # Someone already signed in has no use for the form, so a GET goes straight
    # on. A POST is different: it carries credentials somebody just typed, and
    # bouncing it discarded them silently - sign in as a manager, come back and
    # sign in as a supervisor, and the app kept you as the manager with no error
    # to say why. Credentials submitted are a request to BE that account.
    if current_user.is_authenticated and request.method == "GET":
        return redirect(url_for("views.dashboard"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        # Case-insensitive, to match how accounts are created: admin_create and
        # _ensure_admin both compare lowercased, so "piramon.bu@..." and
        # "Piramon.Bu@..." are already the same account. Requiring the exact
        # original casing here locked people out of their own usernames.
        u = User.query.filter(db.func.lower(User.username) == username.lower()).first()
        if u and u.check_password(password):
            # Read the destination before dropping the old session, and drop it
            # only once the new credentials have proved good - a typo must not
            # log out the person who is already signed in.
            target = _safe_next(session.pop("_login_next", None))
            if current_user.is_authenticated:
                logout_user()
            login_user(u)
            session.permanent = True
            activity.record_login(u, request)
            return redirect(target or url_for("views.dashboard"))
        flash("Invalid username or password.")
        return redirect(url_for("auth.login"))
    # GET: remember where @login_required was sending the user, for after login.
    # Only overwrite when this request actually carries a destination — a
    # background fetch redirected here must not clobber where the user was going.
    target = _safe_next(request.args.get("next"))
    if target:
        session["_login_next"] = target
    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
