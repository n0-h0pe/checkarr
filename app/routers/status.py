from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..queries import get_history, get_service_statuses, get_uptime_buckets
from ..security import require_auth

router = APIRouter(prefix="/api", tags=["status"], dependencies=[Depends(require_auth)])


@router.get("/status", response_model=list[schemas.ServiceStatusOut])
def get_status(db: Session = Depends(get_db)):
    return get_service_statuses(db)


@router.get("/history", response_model=list[schemas.CheckResultOut])
def get_history_route(
    service_ids: list[int] = Query([]),
    check_id: int | None = Query(None),
    minutes: int = Query(1440, ge=0, le=10080),
    limit: int = Query(100, ge=1, le=5000),
    before_id: int | None = Query(None),
    statuses: list[str] = Query([]),
    db: Session = Depends(get_db),
):
    return get_history(db, service_ids, check_id, minutes, limit, before_id, statuses)


@router.get("/uptime")
def get_uptime_route(
    service_id: int = Query(...),
    minutes: int = Query(1440, ge=1, le=10080),
    bars: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return get_uptime_buckets(db, service_id, minutes, bars)
