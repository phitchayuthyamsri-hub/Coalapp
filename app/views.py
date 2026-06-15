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


@bp.route("/routes")
@login_required
def routes():
    return render_template("routes.html")


@bp.route("/timeline")
@login_required
def timeline():
    return render_template("timeline.html")


@bp.route("/pva")
@login_required
def pva():
    return render_template("pva.html")


@bp.route("/subfleet")
@login_required
def subfleet():
    return render_template("subfleet.html")


@bp.route("/performance")
@login_required
def performance():
    return render_template("performance.html")


@bp.route("/daily")
@login_required
def daily():
    return render_template("daily.html")


@bp.route("/guide")
@login_required
def guide():
    return render_template("guide.html")
