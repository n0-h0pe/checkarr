"""The first-boot setup wizard's backend (the wizard itself is
openOnboardingWizard in app.js). Only reports facts the wizard needs to pick
what to show - never the encryption key itself: a key the user is moving
into HC_APP_SECRET_KEY is generated in their own browser, so nothing on
this route can hand out the one that protects stored API keys.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..database import get_db
from ..queries import get_or_create_ui_settings
from ..security import require_auth

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"], dependencies=[Depends(require_auth)])


@router.get("")
def get_onboarding(db: Session = Depends(get_db)):
    return {
        "completed": get_or_create_ui_settings(db).onboarding_completed,
        "encryption": {
            "env_var_set": bool(settings.app_secret_key),
            "key_file_path": str(settings.secret_key_path),
            "key_file_exists": settings.secret_key_path.exists(),
        },
        "auth_enabled": bool(settings.auth_username and settings.auth_password),
        "public_dashboard": {"enabled": settings.public_dashboard_enabled, "port": settings.public_port},
        "service_count": db.query(models.Service).count(),
    }


@router.post("/complete")
def complete_onboarding(db: Session = Depends(get_db)):
    row = get_or_create_ui_settings(db)
    row.onboarding_completed = True
    db.commit()
    return {"completed": True}
