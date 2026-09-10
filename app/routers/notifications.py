from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..queries import get_notifications
from ..security import require_auth

router = APIRouter(prefix="/api/notifications", tags=["notifications"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[schemas.NotificationOut])
def list_notifications(
    active_only: bool = Query(True),
    service_id: int | None = Query(None),
    limit: int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    return get_notifications(db, active_only, service_id, limit)
