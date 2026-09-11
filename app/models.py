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
    # When set, the API key/password is read from this environment variable
    # at call time instead (see security.resolve_secret) and
    # api_key_encrypted is kept empty - "Use environment variable" in the
    # UI, for keeping secrets out of the database/config volume entirely.
    # At most one of the pair is ever populated - see security.apply_secret_field.
    api_key_env_var: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Jellyfin only: some admin-only endpoints (library listing, filesystem
    # browsing) reject the plain API key even when it belongs to an admin -
    # a known Jellyfin inconsistency. Setting both this and `username` (as
    # the admin account's username) makes those specific calls log in as
    # that user instead of using the API key - see jellyfin_client.py.
    jellyfin_admin_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    jellyfin_admin_password_env_var: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
        return bool(self.api_key_encrypted or self.api_key_env_var)

    def has_jellyfin_admin_password(self) -> bool:
        return bool(self.jellyfin_admin_password_encrypted or self.jellyfin_admin_password_env_var)

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
    dashboard (admin and public) renders.

    `card_service_ids` is which services' cards actually show on this
    layout - explicit, not "everything that exists": a newly-created
    service doesn't silently appear on every hand-curated custom layout,
    only on the one is_default layout (see below), which is exempt from
    this list entirely and always shows every service regardless of what's
    stored here. Exactly one row has is_default=True - the protected
    "All Services" layout seeded by get_or_create_active_layout, which
    can't be deleted (see routers/dashboard_layouts.py) and whose card set
    can't be trimmed, unlike ordinary custom layouts."""

    __tablename__ = "dashboard_layouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sizes: Mapped[dict] = mapped_column(JSON, default=dict)
    columns: Mapped[int | None] = mapped_column(Integer, nullable=True)
    card_service_ids: Mapped[list] = mapped_column(JSON, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
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
    Service.api_key_encrypted is - never stored or returned in plaintext -
    or sourced from an environment variable instead via secret_env_var (see
    security.apply_secret_field/resolve_secret). notify_on_warn/
    notify_on_fail gate which severity tier of alert this channel receives
    (see alerting.dispatch_alert)."""

    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Same "Use environment variable" toggle as Service.api_key_env_var -
    # see security.apply_secret_field/resolve_secret.
    secret_env_var: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notify_on_warn: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_fail: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    def has_secret(self) -> bool:
        return bool(self.secret_encrypted or self.secret_env_var)


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
    queries.get_or_create_log_pruning_settings) configuring the recurring
    housekeeping job (see housekeeping.run_housekeeping, scheduled every 30
    minutes by scheduler.schedule_housekeeping) that deletes CheckResult
    ("Log & History") rows older than `retention_days` across every service.
    No time-of-day setting - it just runs on a fixed interval and deletes
    whatever currently qualifies. `prune_hour`/`prune_minute` are legacy
    columns from the old once-daily-at-a-time schedule; left in place
    (unused) rather than dropped, per this file's migration convention of
    only ever adding columns. `last_pruned_at` is just an informational
    "last ran at" readout now."""

    __tablename__ = "log_pruning_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    retention_days: Mapped[int] = mapped_column(Integer, default=7)
    prune_hour: Mapped[int] = mapped_column(Integer, default=2)
    prune_minute: Mapped[int] = mapped_column(Integer, default=0)
    last_pruned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class SelfMonitoringState(Base):
    """Singleton row tracking Checkarr's own health, checked every
    housekeeping run (see housekeeping.check_disk_space). `disk_space_tier`
    is the last tier ('warn'/'fail') an alert was already sent for, or None
    when free space is currently fine - alerts only fire on a *transition*
    between tiers, the same "don't re-alert every cycle while it stays bad"
    rule poller.py already applies to regular checks."""

    __tablename__ = "self_monitoring_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    disk_space_tier: Mapped[str | None] = mapped_column(String(10), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class DashboardSettings(Base):
    """Singleton row (see queries.get_or_create_dashboard_settings)
    controlling what the public dashboard port (8090) shows, independent of
    whatever layout the admin app currently has active/is editing.
    `public_layout_id` is a loose reference (no FK constraint, same style as
    DashboardLayout.card_service_ids' loose id lists) to a DashboardLayout -
    falls back to the default "All Services" layout if unset or if that
    layout was since deleted. `public_compact` hides each card's individual
    check rows on the public dashboard only, leaving just the status badge
    and uptime history - the admin app always shows full detail regardless
    of this flag."""

    __tablename__ = "dashboard_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_layout_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    public_compact: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
