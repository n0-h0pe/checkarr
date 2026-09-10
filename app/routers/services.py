from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..checks.runner import default_checks_for_service_type
from ..database import get_db
from ..scheduler import schedule_service, unschedule_service
from ..security import encrypt_secret, require_auth
from ..serializers import serialize_service as _out

router = APIRouter(prefix="/api/services", tags=["services"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[schemas.ServiceOut])
def list_services(db: Session = Depends(get_db)):
    return [_out(s) for s in db.query(models.Service).order_by(models.Service.name).all()]


@router.post("", response_model=schemas.ServiceOut, status_code=201)
def create_service(payload: schemas.ServiceCreate, db: Session = Depends(get_db)):
    if payload.type not in schemas.SERVICE_TYPES:
        raise HTTPException(400, f"Unknown service type '{payload.type}'")

    service = models.Service(
        name=payload.name,
        type=payload.type,
        local_url=payload.local_url.rstrip("/") if payload.local_url else None,
        remote_url=payload.remote_url.rstrip("/") if payload.remote_url else None,
        api_key_encrypted=encrypt_secret(payload.api_key),
        verify_ssl=payload.verify_ssl,
        enabled=payload.enabled,
        poll_interval_seconds=payload.poll_interval_seconds,
        notes=payload.notes,
    )
    db.add(service)
    db.flush()

    for c in default_checks_for_service_type(payload.type):
        db.add(models.CheckDefinition(service_id=service.id, **c))

    db.commit()
    db.refresh(service)
    schedule_service(service)
    return _out(service)


@router.get("/{service_id}", response_model=schemas.ServiceOut)
def get_service(service_id: int, db: Session = Depends(get_db)):
    service = db.get(models.Service, service_id)
    if not service:
        raise HTTPException(404, "Service not found")
    return _out(service)


@router.put("/{service_id}", response_model=schemas.ServiceOut)
def update_service(service_id: int, payload: schemas.ServiceUpdate, db: Session = Depends(get_db)):
    service = db.get(models.Service, service_id)
    if not service:
        raise HTTPException(404, "Service not found")

    if payload.name is not None:
        service.name = payload.name
    if payload.clear_local_url:
        service.local_url = None
    elif payload.local_url is not None:
        service.local_url = payload.local_url.rstrip("/") or None
    if payload.clear_remote_url:
        service.remote_url = None
    elif payload.remote_url is not None:
        service.remote_url = payload.remote_url.rstrip("/") or None
    if not service.local_url and not service.remote_url:
        raise HTTPException(400, "At least one of local address or remote address must be set")
    if payload.clear_api_key:
        service.api_key_encrypted = None
    elif payload.api_key:
        service.api_key_encrypted = encrypt_secret(payload.api_key)
    if payload.verify_ssl is not None:
        service.verify_ssl = payload.verify_ssl
    if payload.enabled is not None:
        service.enabled = payload.enabled
    if payload.poll_interval_seconds is not None:
        service.poll_interval_seconds = payload.poll_interval_seconds
    if payload.notes is not None:
        service.notes = payload.notes

    db.commit()
    db.refresh(service)

    if service.enabled:
        schedule_service(service)
    else:
        unschedule_service(service.id)

    return _out(service)


@router.delete("/{service_id}", status_code=204)
def delete_service(service_id: int, db: Session = Depends(get_db)):
    service = db.get(models.Service, service_id)
    if not service:
        raise HTTPException(404, "Service not found")
    unschedule_service(service_id)
    db.delete(service)
    db.commit()
    return None


@router.post("/{service_id}/run-now", response_model=list[schemas.CheckResultOut])
async def run_now(service_id: int, db: Session = Depends(get_db)):
    import datetime as dt

    from ..poller import poll_service

    service = db.get(models.Service, service_id)
    if not service:
        raise HTTPException(404, "Service not found")

    before = dt.datetime.now(dt.timezone.utc)
    await poll_service(service_id)
    db.expire_all()
    results = (
        db.query(models.CheckResult)
        .filter(models.CheckResult.service_id == service_id, models.CheckResult.timestamp >= before)
        .order_by(models.CheckResult.timestamp.desc())
        .all()
    )
    return results


@router.get("/{service_id}/checks", response_model=list[schemas.CheckDefinitionOut])
def list_checks(service_id: int, db: Session = Depends(get_db)):
    service = db.get(models.Service, service_id)
    if not service:
        raise HTTPException(404, "Service not found")
    return service.checks


@router.post("/{service_id}/checks", response_model=schemas.CheckDefinitionOut, status_code=201)
def create_check(service_id: int, payload: schemas.CheckDefinitionCreate, db: Session = Depends(get_db)):
    service = db.get(models.Service, service_id)
    if not service:
        raise HTTPException(404, "Service not found")
    if payload.type not in schemas.CHECK_TYPES:
        raise HTTPException(400, f"Unknown check type '{payload.type}'")

    check = models.CheckDefinition(
        service_id=service_id,
        name=payload.name,
        type=payload.type,
        config=payload.config,
        enabled=payload.enabled,
        interval_seconds=payload.interval_seconds,
        is_builtin=False,
    )
    db.add(check)
    db.commit()
    db.refresh(check)
    return check


@router.put("/{service_id}/checks/{check_id}", response_model=schemas.CheckDefinitionOut)
def update_check(
    service_id: int, check_id: int, payload: schemas.CheckDefinitionUpdate, db: Session = Depends(get_db)
):
    check = db.get(models.CheckDefinition, check_id)
    if not check or check.service_id != service_id:
        raise HTTPException(404, "Check not found")

    if payload.name is not None:
        check.name = payload.name
    if payload.type is not None:
        if payload.type not in schemas.CHECK_TYPES:
            raise HTTPException(400, f"Unknown check type '{payload.type}'")
        check.type = payload.type
    if payload.config is not None:
        check.config = payload.config
    if payload.enabled is not None:
        check.enabled = payload.enabled
    if payload.clear_interval:
        check.interval_seconds = None
    elif payload.interval_seconds is not None:
        check.interval_seconds = payload.interval_seconds

    db.commit()
    db.refresh(check)
    return check


@router.delete("/{service_id}/checks/{check_id}", status_code=204)
def delete_check(service_id: int, check_id: int, db: Session = Depends(get_db)):
    check = db.get(models.CheckDefinition, check_id)
    if not check or check.service_id != service_id:
        raise HTTPException(404, "Check not found")
    db.delete(check)
    db.commit()
    return None
