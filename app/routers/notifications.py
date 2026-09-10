from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import require_auth

router = APIRouter(prefix="/api/notifications", tags=["notifications"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[schemas.NotificationOut])
def list_notifications(
    active_only: bool = Query(True),
    service_id: int | None = Query(None),
    limit: int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    q = db.query(models.Notification)
    if active_only:
        q = q.filter(models.Notification.resolved.is_(False))
    if service_id is not None:
        q = q.filter(models.Notification.service_id == service_id)
    return q.order_by(models.Notification.last_seen.desc()).limit(limit).all()
