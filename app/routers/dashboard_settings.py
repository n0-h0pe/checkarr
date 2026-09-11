"""What the public dashboard port (8090) shows - independent of whatever
layout/mode the admin app itself currently has active. See
models.DashboardSettings and queries.get_or_create_dashboard_settings/
get_public_layout.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
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

    require_compact = (
        payload.public_require_compact if payload.public_require_compact is not None else settings_row.public_require_compact
    )
    if payload.clear_public_layout:
        new_layout_id = None
    elif payload.public_layout_id is not None:
        new_layout_id = payload.public_layout_id
    else:
        new_layout_id = settings_row.public_layout_id

    # Enforced here too, not just filtered out of the picker client-side -
    # "these compact layouts are the only thing the public dashboard can be
    # changed to" while this option is on.
    if require_compact and new_layout_id is not None:
        layout = db.get(models.DashboardLayout, new_layout_id)
        if layout and not layout.is_compact:
            raise HTTPException(
                400, "Only compact layouts can be set as the public dashboard layout while that restriction is on"
            )

    if payload.clear_public_layout:
        settings_row.public_layout_id = None
    elif payload.public_layout_id is not None:
        settings_row.public_layout_id = payload.public_layout_id
    if payload.public_require_compact is not None:
        settings_row.public_require_compact = payload.public_require_compact

    db.commit()
    db.refresh(settings_row)
    return settings_row
