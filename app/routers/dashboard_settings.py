"""What the public dashboard port (8090) shows - independent of whatever
layout/mode the admin app itself currently has active. See
models.DashboardSettings and queries.get_or_create_dashboard_settings/
get_public_layout.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..queries import get_or_create_dashboard_settings
from ..security import require_auth

router = APIRouter(prefix="/api/dashboard-settings", tags=["dashboard-settings"], dependencies=[Depends(require_auth)])


@router.get("", response_model=schemas.DashboardSettingsOut)
def get_dashboard_settings(db: Session = Depends(get_db)):
    return get_or_create_dashboard_settings(db)


@router.put("", response_model=schemas.DashboardSettingsOut)
def update_dashboard_settings(payload: schemas.DashboardSettingsUpdate, db: Session = Depends(get_db)):
    settings_row = get_or_create_dashboard_settings(db)

    if payload.clear_public_layout:
        settings_row.public_layout_id = None
    elif payload.public_layout_id is not None:
        settings_row.public_layout_id = payload.public_layout_id

    if payload.clear_public_layout_mobile:
        settings_row.public_layout_id_mobile = None
    elif payload.public_layout_id_mobile is not None:
        settings_row.public_layout_id_mobile = payload.public_layout_id_mobile

    db.commit()
    db.refresh(settings_row)
    return settings_row
