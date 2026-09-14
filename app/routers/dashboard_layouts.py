"""Named, saveable dashboard card-size arrangements, browsable from a
dropdown in the top bar. Exactly one is "active" at a time - that's what
gets rendered (and, on the admin app, resized) on the Dashboard tab.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..queries import get_or_create_active_layout, resolve_layout_for_viewport
from ..security import require_auth

router = APIRouter(prefix="/api/dashboard-layouts", tags=["dashboard-layouts"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[schemas.DashboardLayoutSummary])
def list_layouts(db: Session = Depends(get_db)):
    get_or_create_active_layout(db)  # guarantee at least one exists
    return db.query(models.DashboardLayout).order_by(models.DashboardLayout.name).all()


@router.get("/active", response_model=schemas.DashboardLayoutOut)
def get_active_layout(mobile: bool | None = Query(None), db: Session = Depends(get_db)):
    layout = get_or_create_active_layout(db)
    return resolve_layout_for_viewport(db, layout, mobile)


@router.post("", response_model=schemas.DashboardLayoutOut, status_code=201)
def create_layout(payload: schemas.DashboardLayoutCreate, db: Session = Depends(get_db)):
    if payload.theme is not None and payload.theme not in schemas.THEMES:
        raise HTTPException(400, f"Unknown theme '{payload.theme}'")
    db.query(models.DashboardLayout).filter_by(is_active=True).update({"is_active": False})
    card_service_ids = payload.card_service_ids
    if card_service_ids is None:
        card_service_ids = [sid for (sid,) in db.query(models.Service.id).all()]
    layout = models.DashboardLayout(
        name=payload.name,
        sizes=payload.sizes,
        columns=payload.columns,
        card_service_ids=card_service_ids,
        is_active=True,
        is_compact=payload.is_compact,
        is_mobile=payload.is_mobile,
        theme=payload.theme,
    )
    db.add(layout)
    db.commit()
    db.refresh(layout)
    return layout


@router.get("/{layout_id}", response_model=schemas.DashboardLayoutOut)
def get_layout(layout_id: int, db: Session = Depends(get_db)):
    layout = db.get(models.DashboardLayout, layout_id)
    if not layout:
        raise HTTPException(404, "Layout not found")
    return layout


@router.put("/{layout_id}", response_model=schemas.DashboardLayoutOut)
def update_layout(layout_id: int, payload: schemas.DashboardLayoutUpdate, db: Session = Depends(get_db)):
    layout = db.get(models.DashboardLayout, layout_id)
    if not layout:
        raise HTTPException(404, "Layout not found")
    if payload.card_service_ids is not None and layout.is_default:
        raise HTTPException(400, "The All Services layout always shows every service and can't be trimmed")
    if payload.theme is not None and payload.theme not in schemas.THEMES:
        raise HTTPException(400, f"Unknown theme '{payload.theme}'")
    if payload.name is not None:
        layout.name = payload.name
    if payload.sizes is not None:
        layout.sizes = payload.sizes
    if payload.columns is not None:
        layout.columns = payload.columns
    if payload.card_service_ids is not None:
        layout.card_service_ids = payload.card_service_ids
    if payload.clear_theme:
        layout.theme = None
    elif payload.theme is not None:
        layout.theme = payload.theme
    db.commit()
    db.refresh(layout)
    return layout


@router.post("/{layout_id}/activate", response_model=schemas.DashboardLayoutOut)
def activate_layout(layout_id: int, db: Session = Depends(get_db)):
    layout = db.get(models.DashboardLayout, layout_id)
    if not layout:
        raise HTTPException(404, "Layout not found")
    db.query(models.DashboardLayout).filter_by(is_active=True).update({"is_active": False})
    layout.is_active = True
    db.commit()
    db.refresh(layout)
    return layout


@router.delete("/{layout_id}", status_code=204)
def delete_layout(layout_id: int, db: Session = Depends(get_db)):
    layout = db.get(models.DashboardLayout, layout_id)
    if not layout:
        raise HTTPException(404, "Layout not found")
    if layout.is_default:
        raise HTTPException(400, "The All Services layout can't be deleted")
    was_active = layout.is_active
    db.delete(layout)
    db.commit()
    if was_active:
        get_or_create_active_layout(db)  # activates another, or creates a fresh Default
    return None
