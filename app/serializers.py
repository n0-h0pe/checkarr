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
        icon_type=service.icon_type,
        icon_value=service.icon_value,
        has_api_key=bool(service.api_key_encrypted or service.api_key_env_var),
        api_key_env_var=service.api_key_env_var,
        has_jellyfin_admin_password=bool(service.jellyfin_admin_password_encrypted or service.jellyfin_admin_password_env_var),
        jellyfin_admin_password_env_var=service.jellyfin_admin_password_env_var,
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
        has_secret=bool(channel.secret_encrypted or channel.secret_env_var),
        secret_env_var=channel.secret_env_var,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )


def serialize_service_group(
    group: models.ServiceGroup, all_service_ids: list[int]
) -> schemas.ServiceGroupOut:
    """`all_service_ids` (every current service id) is required for the
    `is_default` ("All Services") group, whose membership is never stored -
    see ServiceGroup's docstring - and harmlessly ignored otherwise."""
    service_ids = all_service_ids if group.is_default else [m.service_id for m in group.members]
    return schemas.ServiceGroupOut(
        id=group.id,
        name=group.name,
        is_default=group.is_default,
        service_ids=service_ids,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


def serialize_downtime_schedule(schedule: models.DowntimeSchedule) -> schemas.DowntimeScheduleOut:
    return schemas.DowntimeScheduleOut(
        id=schedule.id,
        name=schedule.name,
        recurrence=schedule.recurrence,
        start_at=schedule.start_at,
        end_at=schedule.end_at,
        repeat_until=schedule.repeat_until,
        suppress_warn=schedule.suppress_warn,
        suppress_fail=schedule.suppress_fail,
        enabled=schedule.enabled,
        group_ids=[g.group_id for g in schedule.groups],
        is_instant=schedule.is_instant,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )
