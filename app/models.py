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
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    allowed_tabs = db.Column(db.Text)  # JSON list of allowed tab keys; NULL = all tabs
    lang = db.Column(db.String(2), default="en")
    default_page = db.Column(db.String(20))   # tab key to open on login
    can_edit = db.Column(db.Boolean, default=True, nullable=False)
    allowed_apps = db.Column(db.Text)   # JSON list of app keys; NULL = all apps
    # spectator = read-only observer (no submit, no confirm, no upload)
    role = db.Column(db.String(20), default="monitor")
    # spectator | subcontractor | monitor | supervisor | manager | admin
    # Set only for role='subcontractor': which company this login belongs to.
    # It scopes everything they can see to their own trucks.
    subcontractor_id = db.Column(db.Integer, index=True)
    # When this person last cleared their alerts. A confirmed list newer than
    # this is still waiting to be looked at. Held per user rather than per list
    # because the same list is news to the planner and old to the manager who
    # confirmed it.
    alerts_seen_at = db.Column(db.DateTime)

    def set_password(self, pw):
        self.pw_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.pw_hash, pw)


class Truck(db.Model):
    """Fleet entry."""
    id = db.Column(db.Integer, primary_key=True)
    plate = db.Column(db.String(40), unique=True, nullable=False)
    status = db.Column(db.String(20), default="online")  # online/maintenance/breakdown/deactivated
    # The person driving it. Held here rather than on the daily list because a
    # truck keeps its driver across days, and the monitor needs the name beside
    # the plate when a truck is late.
    driver = db.Column(db.String(120), default="")
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
    # The leg's real road distance. Authoritative when set, because the drawn
    # line is thinned for the map and re-summing it loses about a percent -
    # and because summing thousands of points on every plan run is wasteful
    # when the number is already known.
    road_km = db.Column(db.Float)
    speed = db.Column(db.Float, default=40.0)


class Notice(db.Model):
    """Something the operation has been told, and who it was told to.

    The confirmed-list alert is derived from DailyList timestamps, which works
    because confirming is a state change with a time on it. Issuing a revision
    is not: it is a decision that leaves no other trace, so it needs a record of
    its own or there is nothing to alert anyone about afterwards.
    """
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), default="revision")
    day = db.Column(db.String(10), index=True)      # the day at the mine
    subcontractor_id = db.Column(db.Integer, index=True)   # None = all companies
    title = db.Column(db.String(200), default="")
    detail = db.Column(db.JSON)                     # the figures as they stood
    # Which roles this was addressed to, comma separated. Stored rather than
    # inferred so a later change to who counts as "monitoring" cannot silently
    # rewrite who was told at the time.
    audience = db.Column(db.String(120), default="monitor,mine")
    created_by = db.Column(db.String(80), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


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


class LoginEvent(db.Model):
    """One row per successful login (for country / history)."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, index=True)
    username = db.Column(db.String(80))
    ts = db.Column(db.DateTime, default=datetime.utcnow)
    ip = db.Column(db.String(64))
    country = db.Column(db.String(80))
    country_code = db.Column(db.String(4))


class AreaTime(db.Model):
    """Aggregated dwell time per user / area / day."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, index=True)
    username = db.Column(db.String(80))
    page = db.Column(db.String(40))
    day = db.Column(db.String(10))   # YYYY-MM-DD
    seconds = db.Column(db.Integer, default=0)
    __table_args__ = (db.UniqueConstraint("user_id", "page", "day", name="uq_areatime"),)


class ActivityEvent(db.Model):
    """One row per discrete user action (tab open, sort, upload, calc, etc.)."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, index=True)
    username = db.Column(db.String(80))
    ts = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    action = db.Column(db.String(40))   # open_tab | sort | upload | calculate | export | manual_time | language | edit
    detail = db.Column(db.String(300))


class ReturnRoute(db.Model):
    """Per-truck, per-day return-route selection and cost (WI LA-NT-001 §5.3).

    One row per truck per plan date — the route changes daily, so this is a
    record, not an attribute of the truck. Retained so that "route selected and
    cost incurred per truck" is reportable rather than absorbed.
    """
    id = db.Column(db.Integer, primary_key=True)
    plate = db.Column(db.String(40), nullable=False)
    key = db.Column(db.String(40), index=True, nullable=False)   # normalized plate
    plan_date = db.Column(db.String(10), index=True, nullable=False)  # YYYY-MM-DD
    route = db.Column(db.String(10), default="hue")   # hue (default) | ql49
    cost_variance = db.Column(db.Float)               # only for the non-default route
    note = db.Column(db.String(300), default="")
    set_by = db.Column(db.String(80))
    set_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_by = db.Column(db.String(80))
    approved_at = db.Column(db.DateTime)
    __table_args__ = (db.UniqueConstraint("key", "plan_date", name="uq_returnroute"),)


class Shift(db.Model):
    """A monitoring shift. Shifts are DATA, not code - NT can add, remove or
    retime them without a rebuild (the 2-or-3 shift question stays open)."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False)
    start_hhmm = db.Column(db.String(5), default="06:00")   # local time, UTC+7
    end_hhmm = db.Column(db.String(5), default="14:00")
    ordering = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True, nullable=False)


class ShiftCheck(db.Model):
    """One agenda line on a shift. `code` names the corridor event the check
    asks about; it maps onto the Anchor roles the geofence engine already
    detects, so a check is answered from GPS rather than by hand."""
    id = db.Column(db.Integer, primary_key=True)
    shift_id = db.Column(db.Integer, index=True, nullable=False)
    code = db.Column(db.String(30), nullable=False)
    # arrive_mine | load_done | depart_border | depart_ql49 | arrive_port | unload_done
    label = db.Column(db.String(160), default="")
    ordering = db.Column(db.Integer, default=0)


class DailyList(db.Model):
    """The day's truck list as it moves supervisor -> manager.

    draft -> submitted -> confirmed, or submitted -> rejected (back to draft).
    Once confirmed the list is locked: only a manager or an admin may change it.
    """
    id = db.Column(db.Integer, primary_key=True)
    list_date = db.Column(db.String(10), index=True, nullable=False)   # YYYY-MM-DD
    # One list per subcontractor per day - the manager reviews each company's
    # list separately. NULL means a legacy list from before per-sub lists.
    subcontractor_id = db.Column(db.Integer, index=True)
    state = db.Column(db.String(12), default="draft", nullable=False)
    submitted_by = db.Column(db.String(80))
    submitted_at = db.Column(db.DateTime)
    confirmed_by = db.Column(db.String(80))
    confirmed_at = db.Column(db.DateTime)
    rejected_by = db.Column(db.String(80))
    rejected_at = db.Column(db.DateTime)
    reject_reason = db.Column(db.String(400), default="")

    __table_args__ = (db.UniqueConstraint("list_date", "subcontractor_id",
                                          name="uq_daily_list"),)

    @property
    def locked(self):
        return self.state == "confirmed"


class DailyListRow(db.Model):
    """One truck on the day's list.

    Each row carries its own state, separate from the list's. Ticking a truck
    sends it; leaving it unticked holds it as `pending` with a written reason,
    so a truck that is not going is parked rather than deleted and can still be
    sent or rejected later.
    """
    id = db.Column(db.Integer, primary_key=True)
    list_id = db.Column(db.Integer, index=True, nullable=False)
    plate = db.Column(db.String(40), nullable=False)
    key = db.Column(db.String(40), index=True)     # normalised plate
    ready = db.Column(db.Boolean, default=True, nullable=False)   # the tick
    state = db.Column(db.String(10), default="pending")       # pending|approved|denied
    location = db.Column(db.String(60), default="")           # from the sheet
    sheet_status = db.Column(db.String(30), default="")       # Loaded / Empty
    reason = db.Column(db.String(300), default="")  # required when held back (Gap Rule)
    arrive_date = db.Column(db.String(10), default="")  # planned arrival at the mine
    arrive_hhmm = db.Column(db.String(5), default="")
    note = db.Column(db.String(300), default="")


class GpsIngestRun(db.Model):
    """One row per GPS ingestion poll (audit trail + status for /gps-capture)."""
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(40), index=True)   # tct | adsun | ...
    source = db.Column(db.String(120), default="")    # api:tct etc.
    started = db.Column(db.DateTime, default=datetime.utcnow)
    finished = db.Column(db.DateTime)
    fetched = db.Column(db.Integer, default=0)        # rows returned by provider
    inserted = db.Column(db.Integer, default=0)       # new rows stored (dedup'd)
    error = db.Column(db.String(500), default="")

class Subcontractor(db.Model):
    """A haulage company committed to the project."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    short = db.Column(db.String(40), default="")      # what appears in tables
    active = db.Column(db.Boolean, default=True, nullable=False)
    contact = db.Column(db.String(200), default="")
    added = db.Column(db.DateTime, default=datetime.utcnow)


class FleetCommitment(db.Model):
    """One truck committed by one subcontractor for the project.

    This is the contract, not a convenience index. The fleet is agreed up front
    and holds for the project, so a truck cannot leave by quietly missing from
    tomorrow's sheet - it leaves only by an explicit, recorded release. Daily
    readiness is measured against these rows.
    """
    id = db.Column(db.Integer, primary_key=True)
    subcontractor_id = db.Column(db.Integer, index=True, nullable=False)
    plate = db.Column(db.String(40), nullable=False)
    key = db.Column(db.String(40), index=True, nullable=False)   # normalised
    committed_from = db.Column(db.String(10), default="")        # YYYY-MM-DD
    released_on = db.Column(db.String(10), default="")           # set = no longer committed
    release_reason = db.Column(db.String(300), default="")
    released_by = db.Column(db.String(80), default="")
    released_at = db.Column(db.DateTime)
    note = db.Column(db.String(300), default="")
    __table_args__ = (db.UniqueConstraint("subcontractor_id", "key",
                                          name="uq_commitment"),)

    @property
    def committed(self):
        return not self.released_on

class PlanSetting(db.Model):
    """A tunable number the planner uses.

    These are estimates that will be corrected as the operation runs, so they are
    rows rather than constants - changing a loading time or a gate window must not
    require a deployment.
    """
    key = db.Column(db.String(40), primary_key=True)
    value = db.Column(db.String(40), default="")
    label = db.Column(db.String(160), default="")
    unit = db.Column(db.String(20), default="")
    group = db.Column(db.String(30), default="")
    ordering = db.Column(db.Integer, default=0)
    updated_by = db.Column(db.String(80), default="")
    updated_at = db.Column(db.DateTime)


class PlanSnapshot(db.Model):
    """A week's plan, frozen at the moment it was issued.

    The plan the subcontractor works to has to stop moving, for two reasons.
    It is the document they were sent - recomputing it later would quietly
    rewrite what they agreed to. And it is what the revision is compared
    against: a baseline recomputed from today's readiness moves whenever the
    day moves, so every difference cancels itself out and the comparison reads
    zero however badly the day went.

    The figures are stored WITH the rows, because a difference can only be
    attributed to a factor if the assumptions behind the promise are known.
    """
    id = db.Column(db.Integer, primary_key=True)
    week_start = db.Column(db.String(10), index=True, nullable=False)  # Monday
    # Set when this freezes ONE day - a revision issued for that day. NULL means
    # the snapshot is the week, issued in advance. Both are the same act: a plan
    # stops moving at the moment somebody commits to it.
    day = db.Column(db.String(10), index=True)
    # NULL means the snapshot covers every company, planned together.
    subcontractor_id = db.Column(db.Integer, index=True)
    issued_by = db.Column(db.String(80), default="")
    issued_at = db.Column(db.DateTime, default=datetime.utcnow)
    note = db.Column(db.String(300), default="")
    rows = db.Column(db.JSON)        # the planned loops, exactly as issued
    figures = db.Column(db.JSON)     # every planning figure in force that day
