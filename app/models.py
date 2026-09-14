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
    # Overrides the icon a card/row would otherwise show for this service's
    # `type` (see meta.SERVICE_TYPE_ICONS / common.js's typeIcon). Both null
    # (the default) means "just use the type's own icon" - the original
    # behavior. icon_type says how to read icon_value:
    #   "library" -> another entry in SERVICE_TYPE_ICONS, looked up by this
    #                value instead of this service's own `type` (e.g. a
    #                Radarr service rendered with Sonarr's logo)
    #   "emoji"   -> icon_value is the literal emoji character(s) to render
    #                as text, no image involved
    #   "upload"  -> icon_value is the filename of a user-uploaded image
    #                under settings.icons_path, served at /custom-icons/
    #                (see routers/icon_uploads.py) - never rendered as
    #                inline SVG, always via <img src>, so an uploaded SVG
    #                can't execute a script the way it could inline.
    # Editable at any time (unlike DashboardLayout's creation-only flags) -
    # see ServiceUpdate.
    icon_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    icon_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
    # Recorded once, at poll time (see poller.poll_service), not
    # reconstructed later from whatever schedules happen to exist when
    # History is viewed - a permanent audit trail rather than a live
    # lookup, so it stays accurate even after an Instant SDT window (which
    # is deleted once it ends, see routers/downtime.py's reaping) is long
    # gone. Always False for an "ok" result (no alert tier to suppress in
    # the first place) and for anything predating this column.
    in_sdt: Mapped[bool] = mapped_column(Boolean, default=False)

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

    `is_compact` marks this layout as rendering without each card's
    individual check rows, address/last-checked line, or Run now/History
    buttons - just the icon, name, and status badge on one line, then the
    uptime strip on a second (see renderServiceCard in common.js).

    `is_mobile` marks this layout as a single always-full-width column,
    reordered with Move to top/up/down/bottom controls instead of free-form
    drag-to-move/resize - meant for (and, see below, auto-selected on) a
    phone-width screen, where free-form placement has nowhere to drag to
    and a stray desktop x-position used to be able to push a card past the
    edge of the visible grid, creating implicit columns off-screen and
    making the whole page scroll sideways. A mobile layout's `sizes` only
    ever store each card's `y` (its position in the list) and `h` - `x`/`w`
    are never read back from saved data at all, always forced to
    1/full-width, so that bug class can't recur.

    Both flags are set only at creation (DashboardLayoutCreate) and never
    changed afterward - together they split saved layouts into four
    independent pools (Desktop, Desktop-Compact, Mobile, Mobile-Compact),
    never one layout flipped between them. Switching "Compact view" on the
    Dashboard tab switches which pool's layouts are even offered in the
    dropdown, rather than mutating whichever one you're looking at; which
    of the two device pools is offered switches automatically with the
    actual viewport width, no separate button for that - see
    ensureActiveLayout in common.js and resolve_layout_for_viewport in
    queries.py, which fall back to that pool's is_default layout whenever
    the active/pinned one doesn't match the viewport actually asking for it,
    so every pool always has something safe to show.

    `card_service_ids` is which services' cards actually show on this
    layout - explicit, not "everything that exists": a newly-created
    service doesn't silently appear on every hand-curated custom layout.
    Every one of the four pools has exactly one is_default=True layout -
    the protected "All Services" layout for that pool, seeded at startup
    (see database.py's _ensure_default_layouts) if it doesn't already
    exist, which can't be deleted (see routers/dashboard_layouts.py) and
    whose card set can't be trimmed, unlike ordinary custom layouts. See
    Dashboard Settings (DashboardSettings.public_layout_id/
    public_layout_id_mobile below) for which layout the public dashboard
    actually shows.

    `theme` (one of schemas.THEMES, e.g. "oled"/"coder") is this layout's
    own override of Settings > Customizations' admin-wide theme
    (UiSettings.theme below) - None means "just use that". Editable from
    the Dashboard tab's own theme picker (edit mode), not Settings, since
    it's a property of the layout being viewed/edited, not a global. Scoped
    narrowly on the admin side - only #tab-dashboard's background and cards
    switch, the header/nav stay on the admin-wide theme regardless (see the
    data-layout-theme attribute in app.js) - but on the public dashboard
    (which has no separate admin chrome of its own to keep stable) this is
    effectively the whole page's theme, see queries.resolve_public_theme."""

    __tablename__ = "dashboard_layouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sizes: Mapped[dict] = mapped_column(JSON, default=dict)
    columns: Mapped[int | None] = mapped_column(Integer, nullable=True)
    card_service_ids: Mapped[list] = mapped_column(JSON, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_compact: Mapped[bool] = mapped_column(Boolean, default=False)
    is_mobile: Mapped[bool] = mapped_column(Boolean, default=False)
    theme: Mapped[str | None] = mapped_column(String(20), nullable=True)
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

    `is_instant` marks a schedule created via the "Instantly start SDT"
    button rather than the Add schedule form - always `recurrence="once"`,
    always covers the default "All Services" group, and is reaped (deleted)
    once it expires (see routers/downtime.py's list endpoint) rather than
    sticking around the way a user-authored schedule does. Set only at
    creation and never changed afterward, same convention as
    DashboardLayout.is_compact above. Kept separate from the regular
    Schedules list in the UI - it renders as its own banner instead of a
    schedule card - but suppression itself (downtime.is_suppressed) treats
    it exactly like any other enabled schedule, no special-casing needed
    there."""

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
    is_instant: Mapped[bool] = mapped_column(Boolean, default=False)
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

    `public_layout_id` (the Desktop pin) and `public_layout_id_mobile` (the
    Mobile pin) are each a loose reference (no FK constraint, same style as
    DashboardLayout.card_service_ids' loose id lists) to a DashboardLayout -
    picked between by queries.get_public_layout based on the requesting
    viewport, each falling back independently to that pool's own default
    "All Services" layout if unset or if the pinned one was since deleted.
    Whether the public dashboard actually renders compact is entirely a
    property of *which layout* is pinned (DashboardLayout.is_compact
    above), not a separate flag - both dropdowns simply offer every layout
    in their own device pool, compact or not.

    `public_require_compact` and `uptime_bar_count` are both retired.
    `public_require_compact` - the public dashboard used to support
    restricting its pin to compact layouts only, before Mobile layouts
    existed as their own pool; picking a Desktop vs a Mobile layout now
    happens automatically by viewport instead, which made that restriction
    redundant. `uptime_bar_count` was a brief attempt at a single global bar
    count for every card's uptime strip - replaced by a per-card count
    instead (DashboardLayout.sizes[id].bars, see common.js's
    effectiveUptimeBarCount/renderUptimeBarControl) once it turned out a
    count that looked fine on a wide card just broke (bars rendering at
    0-width and disappearing) on a narrower one, with no way to have both
    sizes on one dashboard under a single global number. Both left in place
    unused rather than dropped, same as every other retired column in
    database.py."""

    __tablename__ = "dashboard_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_layout_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    public_layout_id_mobile: Mapped[int | None] = mapped_column(Integer, nullable=True)
    public_require_compact: Mapped[bool] = mapped_column(Boolean, default=False)
    uptime_bar_count: Mapped[int] = mapped_column(Integer, default=20)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class UiSettings(Base):
    """Singleton row (see queries.get_or_create_ui_settings) for Settings >
    Customizations - currently just the admin-wide UI theme (one of
    schemas.THEMES), applied to the whole admin app (header included) and
    used as the fallback on the public dashboard wherever the layout being
    shown doesn't have its own override (see DashboardLayout.theme). A
    separate table rather than another DashboardSettings column since this
    is genuinely a different concern (overall UI appearance, not what the
    public port shows) - Customizations is its own Settings sub-tab, not a
    section of Dashboard Settings."""

    __tablename__ = "ui_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    theme: Mapped[str] = mapped_column(String(20), default="dark")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
