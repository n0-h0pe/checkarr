"""Settings > Customizations - currently just the admin-wide UI theme. See
models.UiSettings and queries.get_or_create_ui_settings/resolve_public_theme.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..queries import get_or_create_ui_settings
from ..security import require_auth

router = APIRouter(prefix="/api/ui-settings", tags=["ui-settings"], dependencies=[Depends(require_auth)])


@router.get("", response_model=schemas.UiSettingsOut)
def get_ui_settings(db: Session = Depends(get_db)):
    return get_or_create_ui_settings(db)


@router.put("", response_model=schemas.UiSettingsOut)
def update_ui_settings(payload: schemas.UiSettingsUpdate, db: Session = Depends(get_db)):
    if payload.theme not in schemas.THEMES:
        raise HTTPException(400, f"Unknown theme '{payload.theme}'")
    settings_row = get_or_create_ui_settings(db)
    settings_row.theme = payload.theme
    db.commit()
    db.refresh(settings_row)
    return settings_row
