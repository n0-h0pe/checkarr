import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..checks.runner import default_checks_for_service_type
from ..config import settings
from ..connection_test import test_connection
from ..database import get_db
from ..library_scan import LibraryScanError, scan_jellyfin_libraries, scan_plex_libraries
from ..scheduler import schedule_service, unschedule_service
from ..security import apply_secret_field, require_auth, resolve_secret
from ..serializers import serialize_service as _out

router = APIRouter(prefix="/api/services", tags=["services"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[schemas.ServiceOut])
def list_services(db: Session = Depends(get_db)):
    return [_out(s) for s in db.query(models.Service).order_by(models.Service.name).all()]


@router.post("/test-connection", response_model=schemas.ConnectionTestResponse)
async def test_connection_route(payload: schemas.ConnectionTestRequest):
    return await test_connection(payload)


@router.post("", response_model=schemas.ServiceOut, status_code=201)
def create_service(payload: schemas.ServiceCreate, db: Session = Depends(get_db)):
    if payload.type not in schemas.SERVICE_TYPES:
        raise HTTPException(400, f"Unknown service type '{payload.type}'")

    service = models.Service(
        name=payload.name,
        type=payload.type,
        local_url=payload.local_url.rstrip("/") if payload.local_url else None,
        remote_url=payload.remote_url.rstrip("/") if payload.remote_url else None,
        check_both_targets=payload.check_both_targets,
        username=payload.username or None,
        enabled=payload.enabled,
        poll_interval_seconds=payload.poll_interval_seconds,
        notes=payload.notes,
    )
    apply_secret_field(
        service, "api_key_encrypted", "api_key_env_var",
        use_env=payload.api_key_use_env, env_var=payload.api_key_env_var, literal_value=payload.api_key,
    )
    apply_secret_field(
        service, "jellyfin_admin_password_encrypted", "jellyfin_admin_password_env_var",
        use_env=payload.jellyfin_admin_password_use_env, env_var=payload.jellyfin_admin_password_env_var,
        literal_value=payload.jellyfin_admin_password,
    )
    db.add(service)
    db.flush()

    for c in default_checks_for_service_type(payload.type):
        db.add(models.CheckDefinition(service_id=service.id, **c))
    _maybe_add_ssl_check(service, db)

    db.commit()
    db.refresh(service)
    schedule_service(service)
    return _out(service)


_SSL_CHECK_TYPE = "ssl_certificate"


def _maybe_add_ssl_check(service: models.Service, db: Session) -> None:
    """Auto-generates the dedicated SSL validity check the first time a
    service gets an https:// address, rather than requiring the user to add
    it by hand - mirrors how default_checks_for_service_type seeds other
    builtins. Only adds one (it runs against whichever target(s) are https -
    never a plain http:// one, see poller.py's target selection for
    ssl_certificate) and never removes it, so switching every address away
    from https just leaves it not polled (last result stays put) instead of
    silently deleting a check the user may have customized (interval, alert
    level)."""
    has_https = any(u and u.startswith("https://") for u in (service.local_url, service.remote_url))
    if not has_https:
        return
    already_has = any(c.type == _SSL_CHECK_TYPE for c in service.checks)
    if already_has:
        return
    db.add(
        models.CheckDefinition(
            service_id=service.id,
            name="SSL certificate valid",
            type=_SSL_CHECK_TYPE,
            config={"expiry_warn_days": 14},
            enabled=True,
            is_builtin=True,
        )
    )


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
    if payload.check_both_targets is not None:
        service.check_both_targets = payload.check_both_targets
    if payload.username is not None:
        service.username = payload.username or None
    apply_secret_field(
        service, "api_key_encrypted", "api_key_env_var",
        use_env=payload.api_key_use_env, env_var=payload.api_key_env_var, literal_value=payload.api_key,
        clear=payload.clear_api_key,
    )
    apply_secret_field(
        service, "jellyfin_admin_password_encrypted", "jellyfin_admin_password_env_var",
        use_env=payload.jellyfin_admin_password_use_env, env_var=payload.jellyfin_admin_password_env_var,
        literal_value=payload.jellyfin_admin_password, clear=payload.clear_jellyfin_admin_password,
    )
    if payload.enabled is not None:
        service.enabled = payload.enabled
    if payload.poll_interval_seconds is not None:
        service.poll_interval_seconds = payload.poll_interval_seconds
    if payload.notes is not None:
        service.notes = payload.notes

    _maybe_add_ssl_check(service, db)

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
    # Not cascaded via an ORM relationship on Service - clean up explicitly
    # so a Service Group never keeps a dangling membership row.
    db.query(models.ServiceGroupMember).filter_by(service_id=service_id).delete()
    # Same for a custom dashboard layout's explicit card list - the
    # is_default "All Services" layout ignores this field entirely, nothing
    # to clean up there.
    for layout in db.query(models.DashboardLayout).filter_by(is_default=False).all():
        if service_id in (layout.card_service_ids or []):
            layout.card_service_ids = [sid for sid in layout.card_service_ids if sid != service_id]
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


@router.post("/{service_id}/scan-libraries", response_model=schemas.LibraryScanResponse)
async def scan_libraries(service_id: int, db: Session = Depends(get_db)):
    service = db.get(models.Service, service_id)
    if not service:
        raise HTTPException(404, "Service not found")
    if service.type not in ("plex", "jellyfin"):
        raise HTTPException(400, "Library scanning is only available for Plex and Jellyfin services")

    base_url = service.local_url or service.remote_url
    if not base_url:
        raise HTTPException(400, "Service has no address configured")

    api_key = resolve_secret(service.api_key_env_var, service.api_key_encrypted)
    jellyfin_admin_password = resolve_secret(service.jellyfin_admin_password_env_var, service.jellyfin_admin_password_encrypted)
    check_type = "plex_filesystem_path" if service.type == "plex" else "jellyfin_filesystem_path"

    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds, verify=False) as client:
        try:
            if service.type == "plex":
                found = await scan_plex_libraries(client, base_url, api_key)
            else:
                found = await scan_jellyfin_libraries(
                    client, base_url, api_key, service.username, jellyfin_admin_password
                )
        except LibraryScanError as exc:
            raise HTTPException(502, str(exc))

    existing_paths = {c.config.get("path") for c in service.checks if c.type == check_type}

    created: list[models.CheckDefinition] = []
    for title, path in found:
        if path in existing_paths:
            continue
        check = models.CheckDefinition(
            service_id=service.id,
            name=f"Library: {title} ({path})",
            type=check_type,
            config={"path": path, "min_entries": 1},
            enabled=True,
            is_builtin=False,
        )
        db.add(check)
        existing_paths.add(path)
        created.append(check)

    db.commit()
    for c in created:
        db.refresh(c)

    return schemas.LibraryScanResponse(
        checks_created=[schemas.CheckDefinitionOut.model_validate(c, from_attributes=True) for c in created],
        paths_found=len(found),
    )


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


@router.post("/{service_id}/checks/reorder", response_model=list[schemas.CheckDefinitionOut])
def reorder_checks(service_id: int, payload: schemas.ChecksReorderRequest, db: Session = Depends(get_db)):
    service = db.get(models.Service, service_id)
    if not service:
        raise HTTPException(404, "Service not found")

    existing_ids = {c.id for c in service.checks}
    if set(payload.ordered_ids) != existing_ids:
        raise HTTPException(400, "ordered_ids must contain exactly this service's current check ids")

    by_id = {c.id: c for c in service.checks}
    for index, check_id in enumerate(payload.ordered_ids):
        by_id[check_id].sort_order = index

    db.commit()
    db.refresh(service)
    return service.checks
