"""Read-only query helpers shared by the full admin app and the restricted
public-dashboard app - keeps the two in lockstep without either importing
the other's routers (the public app must never gain access to anything
mutating or secret-bearing).
"""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models, schemas
from .checks.base import worst_status
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
    db: Session, service_id: int, check_id: int | None, hours: int, limit: int, before_id: int | None = None
) -> list[models.CheckResult]:
    """Ordered by id, not timestamp - id is assigned in insertion order,
    which for a given service's rows already matches timestamp order (ties
    only happen between rows from the same poll, which are contiguous in
    id), so it's a perfectly good sort key and - unlike timestamp, which
    isn't unique - a stable cursor for `before_id` to page against. Offset
    pagination would shift under new rows the poller keeps inserting while
    the user scrolls; a page always "older than id X" can't.
    """
    service = db.get(models.Service, service_id)
    if not service:
        raise HTTPException(404, "Service not found")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = db.query(models.CheckResult).filter(
        models.CheckResult.service_id == service_id, models.CheckResult.timestamp >= cutoff
    )
    if check_id is not None:
        q = q.filter(models.CheckResult.check_id == check_id)
    if before_id is not None:
        q = q.filter(models.CheckResult.id < before_id)
    return q.order_by(models.CheckResult.id.desc()).limit(limit).all()


def get_notifications(
    db: Session, active_only: bool, service_id: int | None, limit: int
) -> list[models.Notification]:
    q = db.query(models.Notification)
    if active_only:
        q = q.filter(models.Notification.resolved.is_(False))
    if service_id is not None:
        q = q.filter(models.Notification.service_id == service_id)
    return q.order_by(models.Notification.last_seen.desc()).limit(limit).all()


def get_service_names(db: Session) -> list[tuple[int, str]]:
    """(id, name) pairs - enough for a dashboard to label notifications/history without exposing full service records."""
    return [(s.id, s.name) for s in db.query(models.Service).order_by(models.Service.name).all()]


DEFAULT_LAYOUT_NAME = "Default"


def get_or_create_active_layout(db: Session) -> models.DashboardLayout:
    """Exactly one DashboardLayout is active at any time. Used both by the
    admin app (to know what to render/resize) and, read-only, by the public
    dashboard (so it mirrors whatever layout is currently selected)."""
    layout = db.query(models.DashboardLayout).filter_by(is_active=True).first()
    if layout:
        return layout

    layout = db.query(models.DashboardLayout).order_by(models.DashboardLayout.id).first()
    if not layout:
        layout = models.DashboardLayout(name=DEFAULT_LAYOUT_NAME, sizes={}, is_active=True)
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
    """Seeds the singleton Log Pruning settings row (defaults: 7 days
    retention, 2am UTC) - idempotent, called once at startup (see
    database.init_db) and by log_pruning.py/routers/log_pruning.py
    whenever the current settings are needed."""
    settings_row = db.query(models.LogPruningSettings).first()
    if settings_row:
        return settings_row
    settings_row = models.LogPruningSettings()
    db.add(settings_row)
    db.commit()
    db.refresh(settings_row)
    return settings_row
