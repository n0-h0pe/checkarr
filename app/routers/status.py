from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..checks.base import worst_status
from ..database import get_db
from ..security import require_auth
from .services import _out

router = APIRouter(prefix="/api", tags=["status"], dependencies=[Depends(require_auth)])


@router.get("/status", response_model=list[schemas.ServiceStatusOut])
def get_status(db: Session = Depends(get_db)):
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
                service=_out(service),
                overall_status=overall,
                last_checked=last_checked,
                latest_results=latest_results,
                active_notification_count=active_notifications,
            )
        )
    return out


@router.get("/history", response_model=list[schemas.CheckResultOut])
def get_history(
    service_id: int = Query(...),
    check_id: int | None = Query(None),
    hours: int = Query(24, ge=1, le=24 * 30),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
):
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
