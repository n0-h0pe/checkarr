from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..log_pruning import prune_all_services
from ..queries import get_or_create_log_pruning_settings
from ..security import require_auth

router = APIRouter(prefix="/api/log-pruning-settings", tags=["log-pruning"], dependencies=[Depends(require_auth)])


@router.get("", response_model=schemas.LogPruningSettingsOut)
def get_log_pruning_settings(db: Session = Depends(get_db)):
    return get_or_create_log_pruning_settings(db)


@router.put("", response_model=schemas.LogPruningSettingsOut)
def update_log_pruning_settings(payload: schemas.LogPruningSettingsUpdate, db: Session = Depends(get_db)):
    settings_row = get_or_create_log_pruning_settings(db)

    if payload.retention_days is not None:
        settings_row.retention_days = payload.retention_days

    db.commit()
    db.refresh(settings_row)
    # Nothing to reschedule - pruning runs on a fixed interval regardless of
    # retention_days (see scheduler.schedule_pruning/PRUNE_INTERVAL_HOURS).
    return settings_row


@router.post("/prune-now", response_model=schemas.PruneNowResult)
def prune_now(db: Session = Depends(get_db)):
    return schemas.PruneNowResult(deleted=prune_all_services(db))
