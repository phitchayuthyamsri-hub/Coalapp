from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user

from .models import db, User
from . import activity

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if not username or not password:
            flash("Username and password required.")
            return redirect(url_for("auth.register"))
        if User.query.filter_by(username=username).first():
            flash("That username is taken.")
            return redirect(url_for("auth.register"))
        u = User(username=username)
        u.set_password(password)
        if User.query.count() == 0:
            u.is_admin = True
        db.session.add(u)
        db.session.commit()
        login_user(u)
        session.permanent = True
        return redirect(url_for("views.dashboard"))
    return render_template("register.html")


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
    if current_user.is_authenticated:
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
            login_user(u)
            session.permanent = True
            activity.record_login(u, request)
            target = _safe_next(session.pop("_login_next", None))
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
