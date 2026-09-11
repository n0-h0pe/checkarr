from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..alerting import send_via_channel
from ..database import get_db
from ..security import encrypt_secret, require_auth
from ..serializers import serialize_notification_channel as _out

router = APIRouter(prefix="/api/notification-channels", tags=["notification-channels"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[schemas.NotificationChannelOut])
def list_channels(db: Session = Depends(get_db)):
    return [_out(c) for c in db.query(models.NotificationChannel).order_by(models.NotificationChannel.name).all()]


@router.post("", response_model=schemas.NotificationChannelOut, status_code=201)
def create_channel(payload: schemas.NotificationChannelCreate, db: Session = Depends(get_db)):
    if payload.type not in schemas.NOTIFICATION_CHANNEL_TYPES:
        raise HTTPException(400, f"Unknown notification channel type '{payload.type}'")

    channel = models.NotificationChannel(
        name=payload.name,
        type=payload.type,
        enabled=payload.enabled,
        config=payload.config,
        secret_encrypted=encrypt_secret(payload.secret),
        notify_on_warn=payload.notify_on_warn,
        notify_on_fail=payload.notify_on_fail,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return _out(channel)


@router.put("/{channel_id}", response_model=schemas.NotificationChannelOut)
def update_channel(channel_id: int, payload: schemas.NotificationChannelUpdate, db: Session = Depends(get_db)):
    channel = db.get(models.NotificationChannel, channel_id)
    if not channel:
        raise HTTPException(404, "Notification channel not found")

    if payload.name is not None:
        channel.name = payload.name
    if payload.enabled is not None:
        channel.enabled = payload.enabled
    if payload.config is not None:
        channel.config = payload.config
    if payload.notify_on_warn is not None:
        channel.notify_on_warn = payload.notify_on_warn
    if payload.notify_on_fail is not None:
        channel.notify_on_fail = payload.notify_on_fail
    if payload.clear_secret:
        channel.secret_encrypted = None
    elif payload.secret:
        channel.secret_encrypted = encrypt_secret(payload.secret)

    db.commit()
    db.refresh(channel)
    return _out(channel)


@router.delete("/{channel_id}", status_code=204)
def delete_channel(channel_id: int, db: Session = Depends(get_db)):
    channel = db.get(models.NotificationChannel, channel_id)
    if not channel:
        raise HTTPException(404, "Notification channel not found")
    db.delete(channel)
    db.commit()
    return None


@router.post("/{channel_id}/test", response_model=schemas.NotificationChannelTestResult)
def test_channel(channel_id: int, db: Session = Depends(get_db)):
    channel = db.get(models.NotificationChannel, channel_id)
    if not channel:
        raise HTTPException(404, "Notification channel not found")
    try:
        send_via_channel(channel, "Checkarr test alert", "This is a test alert from Checkarr's Push Notifications settings.")
    except Exception as exc:  # noqa: BLE001 - reported to the user as a test result, not a 500
        return schemas.NotificationChannelTestResult(ok=False, message=str(exc))
    return schemas.NotificationChannelTestResult(ok=True, message="Test message sent")
