from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..queries import get_active_issues
from ..security import require_auth

router = APIRouter(prefix="/api/notifications", tags=["notifications"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[schemas.ActiveIssueOut])
def list_active_issues(db: Session = Depends(get_db)):
    """Every check currently sitting in warn/fail - "what's failing right
    now", not a historical/arr-health-specific feed (see
    queries.get_active_issues)."""
    return get_active_issues(db)
