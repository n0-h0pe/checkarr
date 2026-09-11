from . import models, schemas


def serialize_service(service: models.Service) -> schemas.ServiceOut:
    return schemas.ServiceOut(
        id=service.id,
        name=service.name,
        type=service.type,
        local_url=service.local_url,
        remote_url=service.remote_url,
        check_both_targets=bool(service.check_both_targets),
        username=service.username,
        enabled=service.enabled,
        poll_interval_seconds=service.poll_interval_seconds,
        notes=service.notes,
        has_api_key=bool(service.api_key_encrypted),
        has_jellyfin_admin_password=bool(service.jellyfin_admin_password_encrypted),
        created_at=service.created_at,
        updated_at=service.updated_at,
        checks=[
            schemas.CheckDefinitionOut.model_validate(c, from_attributes=True) for c in service.checks
        ],
    )


def serialize_notification_channel(channel: models.NotificationChannel) -> schemas.NotificationChannelOut:
    return schemas.NotificationChannelOut(
        id=channel.id,
        name=channel.name,
        type=channel.type,
        enabled=channel.enabled,
        config=channel.config or {},
        notify_on_warn=channel.notify_on_warn,
        notify_on_fail=channel.notify_on_fail,
        has_secret=bool(channel.secret_encrypted),
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )
