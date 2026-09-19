"""Read-only query helpers shared by the full admin app and the restricted
public-dashboard app - keeps the two in lockstep without either importing
the other's routers (the public app must never gain access to anything
mutating or secret-bearing).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models, schemas
from .checks.base import STATUS_FAIL, STATUS_SEVERITY, STATUS_WARN, worst_status
from .serializers import serialize_service


def get_service_statuses(db: Session) -> list[schemas.ServiceStatusOut]:
    out: list[schemas.ServiceStatusOut] = []
    for service in db.query(models.Service).order_by(models.Service.name).all():
        latest_results = []
        for check in service.checks:
            # A check can produce more than one row per poll now (one per
            # local/remote target) - grab every row from its most recent
            # poll, not just a single "latest" row, or the (local) one
            # would silently hide the (remote) one (or vice versa).
            latest_ts = (
                db.query(func.max(models.CheckResult.timestamp))
                .filter(models.CheckResult.check_id == check.id)
                .scalar()
            )
            if latest_ts is None:
                continue
            results = (
                db.query(models.CheckResult)
                .filter(models.CheckResult.check_id == check.id, models.CheckResult.timestamp == latest_ts)
                .order_by(models.CheckResult.check_name)
                .all()
            )
            latest_results.extend(results)

        active_notifications = (
            db.query(models.Notification)
            .filter(models.Notification.service_id == service.id, models.Notification.resolved.is_(False))
            .count()
        )

        if not service.enabled:
            overall = "disabled"
        elif not latest_results:
            overall = "unknown"
        else:
            overall = worst_status([r.status for r in latest_results])

        last_checked = max((r.timestamp for r in latest_results), default=None)

        out.append(
            schemas.ServiceStatusOut(
                service=serialize_service(service),
                overall_status=overall,
                last_checked=last_checked,
                latest_results=latest_results,
                active_notification_count=active_notifications,
            )
        )
    return out


def get_history(
    db: Session,
    service_ids: list[int],
    check_id: int | None,
    minutes: int,
    limit: int,
    before_id: int | None = None,
    statuses: list[str] | None = None,
) -> list[models.CheckResult]:
    """Ordered by id, not timestamp - id is assigned in insertion order,
    which for a given service's rows already matches timestamp order (ties
    only happen between rows from the same poll, which are contiguous in
    id), so it's a perfectly good sort key and - unlike timestamp, which
    isn't unique - a stable cursor for `before_id` to page against. Offset
    pagination would shift under new rows the poller keeps inserting while
    the user scrolls; a page always "older than id X" can't.

    `minutes`, not `hours` - the top-bar range picker offers sub-hour
    options (1/3/5/10/15/30 minutes) that an hours-only cutoff couldn't
    represent at all, silently collapsing every one of them to the same
    "last hour" query.

    `minutes == 0` is "Just the last poll" - not a one-minute time window
    (which would come back empty for any service polled less often than
    once a minute), but the single most recent row per (service, check)
    pair among the selected services, i.e. each check's current result.

    `service_ids` empty means "nothing selected" (the History tab's
    checkbox filter defaults to none checked) - returns no rows without
    even querying, rather than every service's history.

    `statuses`, if given non-empty, restricts to just those result statuses
    (ok/warn/fail) - the History tab's severity filter pills. Empty or None
    means no filtering, same as omitting it entirely (unlike service_ids,
    an empty statuses list isn't itself a "show nothing" signal here - the
    frontend already turns an all-pills-off selection into an empty
    service_ids-style short-circuit before ever calling this).

    `in_sdt` (see CheckResult's docstring) is just whatever's already
    stored on each row - recorded once, at poll time, not recomputed here.
    """
    if not service_ids:
        return []

    if minutes == 0:
        latest = db.query(
            models.CheckResult.service_id,
            models.CheckResult.check_id,
            func.max(models.CheckResult.id).label("max_id"),
        ).filter(models.CheckResult.service_id.in_(service_ids))
        if check_id is not None:
            latest = latest.filter(models.CheckResult.check_id == check_id)
        latest = latest.group_by(models.CheckResult.service_id, models.CheckResult.check_id).subquery()

        q = db.query(models.CheckResult).join(latest, models.CheckResult.id == latest.c.max_id)
        if before_id is not None:
            q = q.filter(models.CheckResult.id < before_id)
        if statuses:
            q = q.filter(models.CheckResult.status.in_(statuses))
        return q.order_by(models.CheckResult.id.desc()).limit(limit).all()

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    q = db.query(models.CheckResult).filter(
        models.CheckResult.service_id.in_(service_ids), models.CheckResult.timestamp >= cutoff
    )
    if check_id is not None:
        q = q.filter(models.CheckResult.check_id == check_id)
    if before_id is not None:
        q = q.filter(models.CheckResult.id < before_id)
    if statuses:
        q = q.filter(models.CheckResult.status.in_(statuses))
    return q.order_by(models.CheckResult.id.desc()).limit(limit).all()


def get_uptime_buckets(db: Session, service_id: int, minutes: int, bar_count: int) -> list[str | None]:
    """The dashboard's per-card uptime strip used to just call get_history
    above with a flat row limit (2000) and bucket the rows client-side. That
    silently truncated the older end of the selected range for any service
    whose checks, combined, produce more than `limit` rows within it - e.g.
    several checks polled every poll cycle, or a short poll interval -
    while a service with one check on a long interval (a simple site
    monitor) never came close. Same underlying history, same time range,
    but some cards showed real gaps as "no data" and others didn't, purely
    based on row volume rather than anything about the range actually being
    covered.

    Fetching only `timestamp`/`status` (not every column get_history's rows
    carry) and bucketing here instead means the only cap on how much of the
    range is covered is the cutoff itself, same as the History tab's export
    already gets by paging through everything with `before_id` - there's no
    row limit here at all. Two narrow columns is cheap for any range/volume
    combination a typical setup produces; the longest offered range is now
    a year, so a service with both a short poll interval and years of
    retained history (LogPruningSettings.retention_days can go up to 3650)
    is the one combination that could make this a genuinely large query -
    still correct, just not instant. Only `bar_count` values ever cross
    back to the client either way.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=minutes)
    rows = (
        db.query(models.CheckResult.timestamp, models.CheckResult.status)
        .filter(models.CheckResult.service_id == service_id, models.CheckResult.timestamp >= cutoff)
        .all()
    )

    range_ms = minutes * 60000
    range_start_ms = cutoff.timestamp() * 1000
    now_ms = now.timestamp() * 1000
    bucket_ms = range_ms / bar_count
    buckets: list[str | None] = [None] * bar_count

    for ts, status in rows:
        t = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        t_ms = t.timestamp() * 1000
        if t_ms < range_start_ms or t_ms > now_ms:
            continue
        idx = min(bar_count - 1, int((t_ms - range_start_ms) // bucket_ms))
        if buckets[idx] is None or STATUS_SEVERITY[status] > STATUS_SEVERITY[buckets[idx]]:
            buckets[idx] = status

    return buckets


def get_notifications(
    db: Session, active_only: bool, service_id: int | None, limit: int
) -> list[models.Notification]:
    q = db.query(models.Notification)
    if active_only:
        q = q.filter(models.Notification.resolved.is_(False))
    if service_id is not None:
        q = q.filter(models.Notification.service_id == service_id)
    return q.order_by(models.Notification.last_seen.desc()).limit(limit).all()


def get_active_issues(db: Session) -> list[schemas.ActiveIssueOut]:
    """Every check currently sitting in warn/fail, across every service -
    what the Notifications tab actually renders (see routers/notifications.py).
    Same "latest result(s) per check" shape as get_service_statuses above,
    just flattened across services and filtered to warn/fail instead of
    folded into one worst-status-per-service badge."""
    out: list[schemas.ActiveIssueOut] = []
    for service in db.query(models.Service).filter_by(enabled=True).order_by(models.Service.name).all():
        for check in service.checks:
            latest_ts = (
                db.query(func.max(models.CheckResult.timestamp))
                .filter(models.CheckResult.check_id == check.id)
                .scalar()
            )
            if latest_ts is None:
                continue
            results = (
                db.query(models.CheckResult)
                .filter(models.CheckResult.check_id == check.id, models.CheckResult.timestamp == latest_ts)
                .all()
            )
            for r in results:
                if r.status not in (STATUS_WARN, STATUS_FAIL):
                    continue
                out.append(
                    schemas.ActiveIssueOut(
                        service_id=service.id,
                        service_name=service.name,
                        service_type=service.type,
                        icon_type=service.icon_type,
                        icon_value=service.icon_value,
                        check_name=r.check_name,
                        check_type=r.check_type,
                        status=r.status,
                        message=r.message,
                        timestamp=r.timestamp,
                    )
                )
    return out


def get_service_names(db: Session) -> list[tuple[int, str]]:
    """(id, name) pairs - enough for a dashboard to label notifications/history without exposing full service records."""
    return [(s.id, s.name) for s in db.query(models.Service).order_by(models.Service.name).all()]


DEFAULT_LAYOUT_NAME = "All Services"


def get_or_create_active_layout(db: Session) -> models.DashboardLayout:
    """Exactly one DashboardLayout is active at any time. Used both by the
    admin app (to know what to render/resize) and, read-only, by the public
    dashboard (so it mirrors whatever layout is currently selected). The
    very first layout ever created for an install is seeded as the
    protected, always-shows-every-service "All Services" layout (is_default)
    - see DashboardLayout's docstring."""
    layout = db.query(models.DashboardLayout).filter_by(is_active=True).first()
    if layout:
        return layout

    layout = db.query(models.DashboardLayout).order_by(models.DashboardLayout.id).first()
    if not layout:
        layout = models.DashboardLayout(
            name=DEFAULT_LAYOUT_NAME, sizes={}, is_active=True, is_default=True, card_service_ids=[], theme="dark"
        )
        db.add(layout)
    else:
        layout.is_active = True
    db.commit()
    db.refresh(layout)
    return layout


ALL_SERVICES_GROUP_NAME = "All Services"


def get_or_create_all_services_group(db: Session) -> models.ServiceGroup:
    """Seeds the one undeletable ServiceGroup every Scheduled Down Time
    schedule can target to cover every service - idempotent, called once at
    startup (see database.init_db). Its membership is never stored (see
    ServiceGroup's docstring); this only ever needs to exist once."""
    group = db.query(models.ServiceGroup).filter_by(is_default=True).first()
    if group:
        return group
    group = models.ServiceGroup(name=ALL_SERVICES_GROUP_NAME, is_default=True)
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


def get_or_create_log_pruning_settings(db: Session) -> models.LogPruningSettings:
    """Seeds the singleton Log & History Pruning settings row (default: 7
    days retention) - idempotent, called once at startup (see
    database.init_db) and by housekeeping.py/routers/log_pruning.py
    whenever the current settings are needed."""
    settings_row = db.query(models.LogPruningSettings).first()
    if settings_row:
        return settings_row
    settings_row = models.LogPruningSettings()
    db.add(settings_row)
    db.commit()
    db.refresh(settings_row)
    return settings_row


def get_or_create_dashboard_settings(db: Session) -> models.DashboardSettings:
    """Seeds the singleton Dashboard Settings row (defaults: no pinned
    public layout for either Desktop or Mobile - each falls back to that
    pool's own default "All Services" layout) - idempotent, called once at
    startup (see database.init_db) and by routers/dashboard_settings.py/
    public.py whenever the current settings are needed."""
    settings_row = db.query(models.DashboardSettings).first()
    if settings_row:
        return settings_row
    settings_row = models.DashboardSettings()
    db.add(settings_row)
    db.commit()
    db.refresh(settings_row)
    return settings_row


def get_or_create_ui_settings(db: Session) -> models.UiSettings:
    """Seeds the singleton Settings > Customizations row (default theme:
    "dark", today's look, unchanged from before Customizations existed) -
    idempotent, called once at startup (see database.init_db) and by
    routers/ui_settings.py/main.py's index route/queries.resolve_public_theme
    whenever the current admin-wide theme is needed."""
    settings_row = db.query(models.UiSettings).first()
    if settings_row:
        return settings_row
    settings_row = models.UiSettings()
    db.add(settings_row)
    db.commit()
    db.refresh(settings_row)
    return settings_row


def resolve_public_theme(db: Session, mobile: bool | None = None) -> str:
    """The theme the public dashboard (all three pages - dashboard/history/
    notifications, for one consistent look across the public site, not just
    the dashboard page itself) actually renders.

    Dashboard Settings' "Public port theme override" (public_theme_override)
    wins outright when set - the public port always shows that theme no
    matter which layout is pinned or what that layout's own theme is, full
    stop. Only when it's unset (the default) does this fall back to
    whichever layout Dashboard Settings currently has pinned for this
    viewport's (see get_public_layout) own theme - every layout always has
    one (see DashboardLayout.theme's docstring; "dark" for a legacy row
    that predates that column existing). Unlike the admin app, there's no
    separate chrome to keep stable here, and Settings > Customizations
    never factors in either way - that only ever controls the admin app's
    own header/nav."""
    settings_row = get_or_create_dashboard_settings(db)
    if settings_row.public_theme_override:
        return settings_row.public_theme_override
    return get_public_layout(db, mobile).theme or "dark"


def get_or_create_self_monitoring_state(db: Session) -> models.SelfMonitoringState:
    """Seeds the singleton row housekeeping.check_disk_space uses to only
    alert on a tier transition rather than every 30-minute cycle."""
    state = db.query(models.SelfMonitoringState).first()
    if state:
        return state
    state = models.SelfMonitoringState()
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def resolve_layout_for_viewport(
    db: Session, layout: models.DashboardLayout | None, mobile: bool | None
) -> models.DashboardLayout | None:
    """Given whichever layout is otherwise active/pinned, and whether the
    requesting client is on a phone-width viewport, substitutes that
    device's own pool's is_default "All Services" layout whenever `layout`
    doesn't already belong to it - a Desktop layout stays active/pinned for
    a desktop visitor, but a phone visitor gets bounced to that install's
    Mobile default instead, never rendered the free-form grid (see
    DashboardLayout.is_mobile's docstring for what that used to do to a
    narrow screen).

    `mobile` is None when the caller has no viewport info to offer (e.g. an
    API client, or a request made before the frontend's first render) - in
    that case `layout` is returned untouched, same as before this existed.
    Read-only: unlike the admin app's explicit "Compact view" switch (which
    persists which layout is active), this never changes what's stored -
    every call re-derives the answer from the actual requesting viewport,
    so there's nothing to remember between visits, and two visitors on
    different devices can never fight over shared state the way persisting
    this would risk on the public dashboard, seen by more than one visitor
    at once."""
    if layout is None or mobile is None or bool(layout.is_mobile) == mobile:
        return layout
    match = (
        db.query(models.DashboardLayout)
        .filter_by(is_default=True, is_mobile=mobile, is_compact=layout.is_compact)
        .first()
    )
    return match or layout


def get_public_layout(db: Session, mobile: bool | None = None) -> models.DashboardLayout:
    """What the public dashboard port (8090) actually renders - independent
    of whatever layout the admin app currently has active (see
    get_or_create_active_layout above). Dashboard Settings pins one layout
    for Desktop visitors (`public_layout_id`) and a separate one for Mobile
    visitors (`public_layout_id_mobile`) - `mobile` picks which of the two
    applies; `None` (no viewport info given, e.g. an API client) falls back
    to the Desktop pin, same as before the Mobile pin existed. Whichever
    one applies falls back further to get_or_create_active_layout if unset
    or if the pinned layout has since been deleted - the caller (public.py)
    still runs the result through resolve_layout_for_viewport afterward, so
    a pin that somehow points at the wrong device pool's layout still gets
    corrected rather than rendered as-is."""
    settings_row = get_or_create_dashboard_settings(db)
    pinned_id = settings_row.public_layout_id_mobile if mobile else settings_row.public_layout_id
    if pinned_id is not None:
        layout = db.get(models.DashboardLayout, pinned_id)
        if layout:
            return layout
    return get_or_create_active_layout(db)
