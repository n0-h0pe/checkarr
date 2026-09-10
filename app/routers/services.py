from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..checks.runner import default_checks_for_service_type
from ..database import get_db
from ..scheduler import schedule_service, unschedule_service
from ..security import encrypt_secret, require_auth

router = APIRouter(prefix="/api/services", tags=["services"], dependencies=[Depends(require_auth)])


def _out(service: models.Service) -> schemas.ServiceOut:
    return schemas.ServiceOut(
        id=service.id,
        name=service.name,
        type=service.type,
        base_url=service.base_url,
        verify_ssl=service.verify_ssl,
        enabled=service.enabled,
        poll_interval_seconds=service.poll_interval_seconds,
        notes=service.notes,
        has_api_key=bool(service.api_key_encrypted),
        created_at=service.created_at,
        updated_at=service.updated_at,
        checks=[
            schemas.CheckDefinitionOut.model_validate(c, from_attributes=True) for c in service.checks
        ],
    )


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
        base_url=payload.base_url.rstrip("/"),
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
    if payload.base_url is not None:
        service.base_url = payload.base_url.rstrip("/")
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
    from ..poller import poll_service

    service = db.get(models.Service, service_id)
    if not service:
        raise HTTPException(404, "Service not found")

    await poll_service(service_id)
    db.expire_all()
    results = (
        db.query(models.CheckResult)
        .filter(models.CheckResult.service_id == service_id)
        .order_by(models.CheckResult.timestamp.desc())
        .limit(len(service.checks) or 10)
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
