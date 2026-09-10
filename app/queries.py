"""Read-only query helpers shared by the full admin app and the restricted
public-dashboard app - keeps the two in lockstep without either importing
the other's routers (the public app must never gain access to anything
mutating or secret-bearing).
"""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import models, schemas
from .checks.base import worst_status
from .serializers import serialize_service


def get_service_statuses(db: Session) -> list[schemas.ServiceStatusOut]:
    out: list[schemas.ServiceStatusOut] = []
    for service in db.query(models.Service).order_by(models.Service.name).all():
        latest_results = []
        for check in service.checks:
            result = (
                db.query(models.CheckResult)
                .filter(models.CheckResult.check_id == check.id)
                .order_by(models.CheckResult.timestamp.desc())
                .first()
            )
            if result:
                latest_results.append(result)

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
    db: Session, service_id: int, check_id: int | None, hours: int, limit: int
) -> list[models.CheckResult]:
    service = db.get(models.Service, service_id)
    if not service:
        raise HTTPException(404, "Service not found")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = db.query(models.CheckResult).filter(
        models.CheckResult.service_id == service_id, models.CheckResult.timestamp >= cutoff
    )
    if check_id is not None:
        q = q.filter(models.CheckResult.check_id == check_id)
    return q.order_by(models.CheckResult.timestamp.desc()).limit(limit).all()


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
