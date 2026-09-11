from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import require_auth
from ..serializers import serialize_downtime_schedule, serialize_service_group

router = APIRouter(tags=["downtime"], dependencies=[Depends(require_auth)])


def _all_service_ids(db: Session) -> list[int]:
    return [s.id for s in db.query(models.Service.id).all()]


# ---------- service groups ----------


@router.get("/api/service-groups", response_model=list[schemas.ServiceGroupOut])
def list_service_groups(db: Session = Depends(get_db)):
    all_ids = _all_service_ids(db)
    groups = db.query(models.ServiceGroup).order_by(models.ServiceGroup.is_default.desc(), models.ServiceGroup.name).all()
    return [serialize_service_group(g, all_ids) for g in groups]


@router.post("/api/service-groups", response_model=schemas.ServiceGroupOut, status_code=201)
def create_service_group(payload: schemas.ServiceGroupCreate, db: Session = Depends(get_db)):
    group = models.ServiceGroup(name=payload.name)
    db.add(group)
    db.flush()
    for service_id in set(payload.service_ids):
        db.add(models.ServiceGroupMember(group_id=group.id, service_id=service_id))
    db.commit()
    db.refresh(group)
    return serialize_service_group(group, _all_service_ids(db))


@router.put("/api/service-groups/{group_id}", response_model=schemas.ServiceGroupOut)
def update_service_group(group_id: int, payload: schemas.ServiceGroupUpdate, db: Session = Depends(get_db)):
    group = db.get(models.ServiceGroup, group_id)
    if not group:
        raise HTTPException(404, "Service group not found")
    if group.is_default and (payload.service_ids is not None):
        raise HTTPException(400, "'All Services' membership can't be edited - it always covers every service")

    if payload.name is not None:
        group.name = payload.name
    if payload.service_ids is not None:
        db.query(models.ServiceGroupMember).filter_by(group_id=group.id).delete()
        for service_id in set(payload.service_ids):
            db.add(models.ServiceGroupMember(group_id=group.id, service_id=service_id))

    db.commit()
    db.refresh(group)
    return serialize_service_group(group, _all_service_ids(db))


@router.delete("/api/service-groups/{group_id}", status_code=204)
def delete_service_group(group_id: int, db: Session = Depends(get_db)):
    group = db.get(models.ServiceGroup, group_id)
    if not group:
        raise HTTPException(404, "Service group not found")
    if group.is_default:
        raise HTTPException(400, "'All Services' can't be deleted")
    # Not cascaded via an ORM relationship (DowntimeScheduleGroup belongs to
    # DowntimeSchedule, not to ServiceGroup) - clean up explicitly so a
    # schedule never keeps a dangling link to a deleted group.
    db.query(models.DowntimeScheduleGroup).filter_by(group_id=group_id).delete()
    db.delete(group)
    db.commit()
    return None


# ---------- downtime schedules ----------


def _apply_schedule_validation(name, recurrence, start_at, end_at, suppress_warn, suppress_fail):
    if recurrence not in schemas.RECURRENCE_TYPES:
        raise HTTPException(400, f"Unknown recurrence '{recurrence}'")
    if not suppress_warn and not suppress_fail:
        raise HTTPException(400, "A schedule must suppress at least Warn or Fail")
    if end_at <= start_at:
        raise HTTPException(400, "End must be after start")


@router.get("/api/downtime-schedules", response_model=list[schemas.DowntimeScheduleOut])
def list_downtime_schedules(db: Session = Depends(get_db)):
    schedules = db.query(models.DowntimeSchedule).order_by(models.DowntimeSchedule.name).all()
    return [serialize_downtime_schedule(s) for s in schedules]


@router.post("/api/downtime-schedules", response_model=schemas.DowntimeScheduleOut, status_code=201)
def create_downtime_schedule(payload: schemas.DowntimeScheduleCreate, db: Session = Depends(get_db)):
    schedule = models.DowntimeSchedule(
        name=payload.name,
        recurrence=payload.recurrence,
        start_at=payload.start_at,
        end_at=payload.end_at,
        repeat_until=payload.repeat_until,
        suppress_warn=payload.suppress_warn,
        suppress_fail=payload.suppress_fail,
        enabled=payload.enabled,
    )
    db.add(schedule)
    db.flush()
    for group_id in set(payload.group_ids):
        db.add(models.DowntimeScheduleGroup(schedule_id=schedule.id, group_id=group_id))
    db.commit()
    db.refresh(schedule)
    return serialize_downtime_schedule(schedule)


@router.put("/api/downtime-schedules/{schedule_id}", response_model=schemas.DowntimeScheduleOut)
def update_downtime_schedule(
    schedule_id: int, payload: schemas.DowntimeScheduleUpdate, db: Session = Depends(get_db)
):
    schedule = db.get(models.DowntimeSchedule, schedule_id)
    if not schedule:
        raise HTTPException(404, "Schedule not found")

    if payload.name is not None:
        schedule.name = payload.name
    if payload.recurrence is not None:
        schedule.recurrence = payload.recurrence
    if payload.start_at is not None:
        schedule.start_at = payload.start_at
    if payload.end_at is not None:
        schedule.end_at = payload.end_at
    if payload.clear_repeat_until:
        schedule.repeat_until = None
    elif payload.repeat_until is not None:
        schedule.repeat_until = payload.repeat_until
    if payload.suppress_warn is not None:
        schedule.suppress_warn = payload.suppress_warn
    if payload.suppress_fail is not None:
        schedule.suppress_fail = payload.suppress_fail
    if payload.enabled is not None:
        schedule.enabled = payload.enabled

    _apply_schedule_validation(
        schedule.name, schedule.recurrence, schedule.start_at, schedule.end_at,
        schedule.suppress_warn, schedule.suppress_fail,
    )

    if payload.group_ids is not None:
        db.query(models.DowntimeScheduleGroup).filter_by(schedule_id=schedule.id).delete()
        for group_id in set(payload.group_ids):
            db.add(models.DowntimeScheduleGroup(schedule_id=schedule.id, group_id=group_id))

    db.commit()
    db.refresh(schedule)
    return serialize_downtime_schedule(schedule)


@router.delete("/api/downtime-schedules/{schedule_id}", status_code=204)
def delete_downtime_schedule(schedule_id: int, db: Session = Depends(get_db)):
    schedule = db.get(models.DowntimeSchedule, schedule_id)
    if not schedule:
        raise HTTPException(404, "Schedule not found")
    db.delete(schedule)
    db.commit()
    return None
