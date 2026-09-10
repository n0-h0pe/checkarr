"""Backs the Settings page's "Save Changes" button: applies every staged
quick-edit (Enabled toggle, alert-level toggle) and staged deletion across
however many checks/services were touched, in one request instead of one
round trip per row.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import require_auth

router = APIRouter(prefix="/api/checks", tags=["checks"], dependencies=[Depends(require_auth)])


@router.delete("/{check_id}", status_code=204)
def delete_check(check_id: int, db: Session = Depends(get_db)):
    """Flat delete-by-id, used by Settings' staged-deletion Save flow, which
    tracks only check ids (not which service each belongs to)."""
    check = db.get(models.CheckDefinition, check_id)
    if not check:
        raise HTTPException(404, "Check not found")
    db.delete(check)
    db.commit()
    return None


@router.post("/bulk-update", response_model=schemas.CheckBulkUpdateResponse)
def bulk_update_checks(payload: schemas.CheckBulkUpdateRequest, db: Session = Depends(get_db)):
    updated: list[models.CheckDefinition] = []
    skipped: list[int] = []

    for item in payload.updates:
        check = db.get(models.CheckDefinition, item.check_id)
        if not check:
            # Deleted by someone else since the page loaded - skip rather
            # than failing the whole batch over one stale row.
            skipped.append(item.check_id)
            continue
        if item.enabled is not None:
            check.enabled = item.enabled
        if item.config is not None:
            check.config = item.config
        updated.append(check)

    db.commit()
    for c in updated:
        db.refresh(c)

    return schemas.CheckBulkUpdateResponse(
        updated=[schemas.CheckDefinitionOut.model_validate(c, from_attributes=True) for c in updated],
        skipped_ids=skipped,
    )
