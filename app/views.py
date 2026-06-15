from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user

bp = Blueprint("views", __name__)


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("views.dashboard"))
    return redirect(url_for("auth.login"))


@bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user)


@bp.route("/fleet")
@login_required
def fleet():
    return render_template("fleet.html")
