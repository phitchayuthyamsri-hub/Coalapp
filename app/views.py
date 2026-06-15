import os
from flask import Blueprint, render_template, redirect, url_for, send_from_directory
from flask_login import login_required, current_user

bp = Blueprint("views", __name__)


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("views.performance"))
    return redirect(url_for("auth.login"))


@bp.route("/performance")
@login_required
def performance():
    return render_template("performance.html")


@bp.route("/daily")
@login_required
def daily():
    return render_template("daily.html")


@bp.route("/pva")
@login_required
def pva():
    return render_template("pva.html")


@bp.route("/subfleet")
@login_required
def subfleet():
    return render_template("subfleet.html")


@bp.route("/parameter")
@login_required
def parameter():
    return render_template("parameter.html")


@bp.route("/data")
@login_required
def data():
    return render_template("data.html")


@bp.route("/gps")
@login_required
def gps():
    return render_template("gps.html")


@bp.route("/plan")
@login_required
def plan():
    return render_template("plan.html")


@bp.route("/truckstatus")
@login_required
def truckstatus():
    return render_template("truckstatus.html")


@bp.route("/weigh")
@login_required
def weigh():
    return render_template("weigh.html")


@bp.route("/fleet")
@login_required
def fleet():
    return render_template("fleet.html")


@bp.route("/guide")
@login_required
def guide():
    return render_template("guide.html")


@bp.route("/dashboard")
@login_required
def dashboard():
    return redirect(url_for("views.gps"))


@bp.route("/routes")
@login_required
def routes():
    return redirect(url_for("views.data"))


@bp.route("/timeline")
@login_required
def timeline():
    return redirect(url_for("views.data"))


@bp.route("/tool")
@login_required
def tool():
    folder = os.path.join(os.path.dirname(__file__), "tool")
    return send_from_directory(folder, "index.html")
