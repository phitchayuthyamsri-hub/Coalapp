"""
Database models. SQLite by default; one shared dataset for the whole team.
Users exist only for login — operational data is global (shared source of truth).
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    pw_hash = db.Column(db.String(255), nullable=False)
    created = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pw):
        self.pw_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.pw_hash, pw)


class Truck(db.Model):
    """Fleet entry."""
    id = db.Column(db.Integer, primary_key=True)
    plate = db.Column(db.String(40), unique=True, nullable=False)
    status = db.Column(db.String(20), default="online")  # online/maintenance/breakdown/deactivated
    phone = db.Column(db.String(40), default="")
    gps_provider = db.Column(db.String(40), default="")
    eff_from = db.Column(db.String(10), default="")  # YYYY-MM-DD
    eff_to = db.Column(db.String(10), default="")
    added = db.Column(db.DateTime, default=datetime.utcnow)


class GpsPing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plate = db.Column(db.String(40), index=True, nullable=False)
    dt = db.Column(db.DateTime, index=True, nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    speed = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(40), default="")
    source = db.Column(db.String(120), default="")


class Anchor(db.Model):
    """Geofence zone. polygon stored as JSON list of [lat,lng]."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    color = db.Column(db.String(20), default="#34c759")
    category = db.Column(db.String(40), default="")
    polygon = db.Column(db.JSON, nullable=False)
    min_dwell_min = db.Column(db.Integer, default=5)
    role = db.Column(db.String(20), default="")  # xppl/loading/border/ql49/ql49b/ql49p/port/detour


class RouteLeg(db.Model):
    """Per-leg polyline + speed. points stored as JSON list of [lat,lng]."""
    id = db.Column(db.Integer, primary_key=True)
    leg_key = db.Column(db.String(40), unique=True, nullable=False)
    label = db.Column(db.String(120), default="")
    points = db.Column(db.JSON)  # None until drawn
    speed = db.Column(db.Float, default=40.0)


class DispatchPlanRow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plate = db.Column(db.String(40))
    key = db.Column(db.String(40), index=True)
    load_start = db.Column(db.DateTime)
    port_arrive = db.Column(db.DateTime)


class LoadActualRow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plate = db.Column(db.String(40))
    key = db.Column(db.String(40), index=True)
    load_in = db.Column(db.DateTime)
    net = db.Column(db.Float)
    ticket = db.Column(db.String(80), default="")


class SubFleetRow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plate = db.Column(db.String(40))
    key = db.Column(db.String(40), index=True)
    declared_haul = db.Column(db.String(20), default="")
    claimed_arrive_mine = db.Column(db.DateTime)


class KVStore(db.Model):
    """Shared key-value mirror of the full tool's localStorage (team-wide)."""
    key = db.Column(db.String(255), primary_key=True)
    value = db.Column(db.Text)
