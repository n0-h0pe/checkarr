from datetime import datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)  # radarr/sonarr/prowlarr/plex/jellyfin/generic
    local_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    remote_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    check_both_targets: Mapped[bool] = mapped_column(Boolean, default=False)
    # Plaintext (not sensitive - usernames aren't secrets) login name for
    # services that authenticate with username+password/secret rather than
    # a bearer API key (qBittorrent, rTorrent via HTTP Basic Auth). The
    # paired secret always lives in api_key_encrypted regardless of what
    # it semantically is for a given service type (API key / token /
    # password) - one encrypted slot, reused.
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Jellyfin only: some admin-only endpoints (library listing, filesystem
    # browsing) reject the plain API key even when it belongs to an admin -
    # a known Jellyfin inconsistency. Setting both this and `username` (as
    # the admin account's username) makes those specific calls log in as
    # that user instead of using the API key - see jellyfin_client.py.
    jellyfin_admin_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    poll_interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    # Ordered by sort_order (id as a tiebreak, so every pre-existing row -
    # which all default to 0 - keeps today's creation-order ordering
    # unchanged until a service's checks are actually dragged into a new
    # order). This is what makes Settings' drag-reorder show up on the
    # Dashboard too: get_service_statuses() (queries.py) builds each card's
    # check list straight from this relationship.
    checks: Mapped[list["CheckDefinition"]] = relationship(
        back_populates="service", cascade="all, delete-orphan",
        order_by="CheckDefinition.sort_order, CheckDefinition.id",
    )
    results: Mapped[list["CheckResult"]] = relationship(
        back_populates="service", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="service", cascade="all, delete-orphan"
    )

    def has_api_key(self) -> bool:
        return bool(self.api_key_encrypted)

    def has_jellyfin_admin_password(self) -> bool:
        return bool(self.jellyfin_admin_password_encrypted)

    def get_targets(self) -> list[tuple[str, str]]:
        """(label, url) pairs for whichever of local/remote address are set."""
        targets: list[tuple[str, str]] = []
        if self.local_url:
            targets.append(("local", self.local_url.rstrip("/")))
        if self.remote_url:
            targets.append(("remote", self.remote_url.rstrip("/")))
        return targets


class CheckDefinition(Base):
    __tablename__ = "check_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    service: Mapped["Service"] = relationship(back_populates="checks")


class CheckResult(Base):
    __tablename__ = "check_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False)
    check_id: Mapped[int | None] = mapped_column(ForeignKey("check_definitions.id"), nullable=True)
    check_name: Mapped[str] = mapped_column(String(120))
    check_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(10))  # ok / warn / fail
    message: Mapped[str] = mapped_column(Text, default="")
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    service: Mapped["Service"] = relationship(back_populates="results")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(50))  # e.g. radarr_health
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(10))  # ok/notice/warning/error
    message: Mapped[str] = mapped_column(Text)
    wiki_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    service: Mapped["Service"] = relationship(back_populates="notifications")


class DashboardLayout(Base):
    """A named, saveable arrangement of dashboard cards. `sizes` maps
    service id (as a string, since JSON object keys must be strings) to
    {"w": int, "h": int, "x": int, "y": int} in grid units - x/y are the
    card's 1-based grid-line position, omitted for a card that hasn't been
    manually placed yet (it's auto-packed into the remaining space on
    render instead). `columns` is the grid-column count the browser window
    was showing the last time this layout was edited - the frontend uses it
    to tell "the window is narrower than this layout was arranged for, wrap
    cards to fit" (a purely visual, unsaved re-flow) apart from "this is a
    brand new layout with no width on record yet" (columns is None).
    Exactly one row has is_active=True at a time - that's what the
    dashboard (admin and public) renders."""

    __tablename__ = "dashboard_layouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sizes: Mapped[dict] = mapped_column(JSON, default=dict)
    columns: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class NotificationChannel(Base):
    """An outbound alerting destination (email today; Discord/Pushbullet/etc.
    later) - `type` selects which fields in `config` matter and which sender
    in app/notifiers/ handles it (see alerting.py). `config` holds every
    non-secret setting for that type (e.g. email's smtp_host/port/username/
    from_address/to_addresses); `secret_encrypted` is the one secret slot a
    channel type needs (email's SMTP password), encrypted the same way
    Service.api_key_encrypted is - never stored or returned in plaintext.
    notify_on_warn/notify_on_fail gate which severity tier of alert this
    channel receives (see alerting.dispatch_alert)."""

    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    notify_on_warn: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_fail: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    def has_secret(self) -> bool:
        return bool(self.secret_encrypted)


class ServiceGroup(Base):
    """A named set of services a DowntimeSchedule can target. The seeded
    `is_default` row ("All Services") deliberately stores no membership rows
    at all - membership is computed as "every service that currently exists"
    at read/evaluation time instead (see queries.get_or_create_all_services_group
    and downtime.is_suppressed), so it can never drift out of sync as
    services are added or removed."""

    __tablename__ = "service_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    members: Mapped[list["ServiceGroupMember"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class ServiceGroupMember(Base):
    __tablename__ = "service_group_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("service_groups.id"), nullable=False)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False)

    group: Mapped["ServiceGroup"] = relationship(back_populates="members")


class DowntimeSchedule(Base):
    """A maintenance window during which Push Notifications alerts (not
    check results, not the Notifications tab - just the outbound alert
    dispatch, see downtime.is_suppressed) are suppressed for whichever
    services its linked ServiceGroups cover.

    `start_at`/`end_at` are stored in UTC (the frontend converts from/to the
    browser's local time at the API boundary, same convention as every other
    timestamp in this app). For "once", they're literal - the schedule is
    active for exactly that one range. For a recurring `recurrence`, their
    DATE components instead supply the recurrence pattern (weekday for
    weekly, day-of-month for monthly, month+day for yearly - daily has no
    pattern beyond "every day") while `end_at - start_at` is the window's
    duration, reapplied to each occurrence - see downtime._schedule_active.
    """

    __tablename__ = "downtime_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    recurrence: Mapped[str] = mapped_column(String(10), nullable=False)  # once/daily/weekly/monthly/yearly
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    repeat_until: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    suppress_warn: Mapped[bool] = mapped_column(Boolean, default=True)
    suppress_fail: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    groups: Mapped[list["DowntimeScheduleGroup"]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan"
    )


class DowntimeScheduleGroup(Base):
    __tablename__ = "downtime_schedule_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("downtime_schedules.id"), nullable=False)
    group_id: Mapped[int] = mapped_column(ForeignKey("service_groups.id"), nullable=False)

    schedule: Mapped["DowntimeSchedule"] = relationship(back_populates="groups")


class LogPruningSettings(Base):
    """Singleton row (exactly one, seeded at startup - see
    queries.get_or_create_log_pruning_settings) configuring the one daily
    scheduled job (see log_pruning.py, scheduler.schedule_log_pruning) that
    deletes CheckResult rows older than `retention_days` across every
    service. `prune_hour`/`prune_minute` are UTC (the frontend converts
    from/to the browser's local time at the API boundary, same convention as
    Scheduled Down Time's schedule times). `last_pruned_at` drives
    log_pruning.catch_up_if_needed - if the configured time already passed
    since the last prune (e.g. the container was offline at 2am), it prunes
    immediately at startup instead of waiting up to 24h for the next run."""

    __tablename__ = "log_pruning_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    retention_days: Mapped[int] = mapped_column(Integer, default=7)
    prune_hour: Mapped[int] = mapped_column(Integer, default=2)
    prune_minute: Mapped[int] = mapped_column(Integer, default=0)
    last_pruned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
