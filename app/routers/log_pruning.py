from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..log_pruning import prune_all_services
from ..queries import get_or_create_log_pruning_settings
from ..scheduler import schedule_log_pruning
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
    if payload.prune_hour is not None:
        settings_row.prune_hour = payload.prune_hour
    if payload.prune_minute is not None:
        settings_row.prune_minute = payload.prune_minute

    db.commit()
    db.refresh(settings_row)

    # Takes effect immediately, no restart needed - re-registering the same
    # job id just replaces its trigger (see scheduler.schedule_log_pruning).
    schedule_log_pruning(settings_row.prune_hour, settings_row.prune_minute)
    return settings_row


@router.post("/prune-now", response_model=schemas.PruneNowResult)
def prune_now(db: Session = Depends(get_db)):
    return schemas.PruneNowResult(deleted=prune_all_services(db))
