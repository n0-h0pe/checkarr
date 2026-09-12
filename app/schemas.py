from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

SERVICE_TYPES = [
    "radarr",
    "sonarr",
    "prowlarr",
    "lidarr",
    "whisparr",
    "chaptarr",
    "plex",
    "jellyfin",
    "qbittorrent",
    "deluge",
    "rtorrent",
    "rutorrent",
    "overseerr",
    "jellyseerr",
    "immich",
    "dispatcharr",
    "sportarr",
    "cleanuparr",
    "generic",
]
CHECK_TYPES = [
    "http_200",
    "keyword_match",
    "filesystem_path",
    "arr_system_status",
    "arr_root_folder",
    "arr_disk_space",
    "arr_health",
    "arr_filesystem_path",
    "plex_identity",
    "plex_remote_access",
    "plex_filesystem_path",
    "jellyfin_health",
    "jellyfin_filesystem_path",
    "qbittorrent_login",
    "deluge_login",
    "qbittorrent_disk_space",
    "deluge_disk_space",
    "rtorrent_rpc_status",
    "ftp_path",
    "overseerr_status",
    "overseerr_tmdb_status",
    "ssl_certificate",
    "immich_server_status",
    "immich_storage",
    "immich_jobs",
]

NOTIFICATION_CHANNEL_TYPES = ["email"]


class CheckDefinitionBase(BaseModel):
    name: str
    type: str
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    interval_seconds: int | None = None


class CheckDefinitionCreate(CheckDefinitionBase):
    pass


class CheckDefinitionUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    interval_seconds: int | None = None
    clear_interval: bool = False


class CheckDefinitionOut(CheckDefinitionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    service_id: int
    is_builtin: bool
    sort_order: int


class ChecksReorderRequest(BaseModel):
    ordered_ids: list[int]


ICON_TYPES = ["library", "emoji", "upload"]


class ServiceBase(BaseModel):
    name: str
    type: str
    local_url: str | None = None
    remote_url: str | None = None
    check_both_targets: bool = False
    username: str | None = None
    enabled: bool = True
    poll_interval_seconds: int | None = None
    notes: str | None = None
    # Icon override - see models.Service.icon_type's docstring. Both null
    # (the default) falls back to the type's own icon.
    icon_type: str | None = None
    icon_value: str | None = None

    @model_validator(mode="after")
    def _require_an_address(self):
        if not self.local_url and not self.remote_url:
            raise ValueError("At least one of local_url or remote_url must be set")
        return self

    @model_validator(mode="after")
    def _validate_icon(self):
        if self.icon_type is not None and self.icon_type not in ICON_TYPES:
            raise ValueError(f"Unknown icon_type '{self.icon_type}'")
        if self.icon_type is not None and not self.icon_value:
            raise ValueError("icon_value is required when icon_type is set")
        return self


class ServiceCreate(ServiceBase):
    api_key: str | None = None
    api_key_use_env: bool | None = None
    api_key_env_var: str | None = None
    jellyfin_admin_password: str | None = None
    jellyfin_admin_password_use_env: bool | None = None
    jellyfin_admin_password_env_var: str | None = None


class ServiceUpdate(BaseModel):
    name: str | None = None
    local_url: str | None = None
    remote_url: str | None = None
    clear_local_url: bool = False
    clear_remote_url: bool = False
    check_both_targets: bool | None = None
    username: str | None = None
    api_key: str | None = None
    clear_api_key: bool = False
    api_key_use_env: bool | None = None
    api_key_env_var: str | None = None
    jellyfin_admin_password: str | None = None
    clear_jellyfin_admin_password: bool = False
    jellyfin_admin_password_use_env: bool | None = None
    jellyfin_admin_password_env_var: str | None = None
    enabled: bool | None = None
    poll_interval_seconds: int | None = None
    notes: str | None = None
    icon_type: str | None = None
    icon_value: str | None = None
    # Explicit reset back to the type's own default icon - null icon_type/
    # icon_value in the payload just means "not touching this", same
    # omitted-vs-null ambiguity every other clearable field here works
    # around the same way (clear_local_url etc above).
    clear_icon: bool = False

    @model_validator(mode="after")
    def _validate_icon(self):
        if self.icon_type is not None and self.icon_type not in ICON_TYPES:
            raise ValueError(f"Unknown icon_type '{self.icon_type}'")
        if self.icon_type is not None and not self.icon_value:
            raise ValueError("icon_value is required when icon_type is set")
        return self


class ServiceOut(ServiceBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    has_api_key: bool
    api_key_env_var: str | None = None
    has_jellyfin_admin_password: bool
    jellyfin_admin_password_env_var: str | None = None
    created_at: datetime
    updated_at: datetime
    checks: list[CheckDefinitionOut] = Field(default_factory=list)


class CheckResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    service_id: int
    check_id: int | None
    check_name: str
    check_type: str
    status: str
    message: str
    response_time_ms: float | None
    timestamp: datetime
    # Whether an alert for this result would have been suppressed by
    # Scheduled Down Time at the moment it happened (see
    # downtime.SuppressionContext.was_suppressed, which computes this in
    # queries.get_history) - always False for an "ok" result, since there's
    # no alert tier to suppress in the first place.
    in_sdt: bool = False


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    service_id: int
    source: str
    severity: str
    message: str
    wiki_url: str | None
    first_seen: datetime
    last_seen: datetime
    resolved: bool
    resolved_at: datetime | None


class ActiveIssueOut(BaseModel):
    """One check currently sitting in warn/fail - what the Notifications tab
    actually shows now (see queries.get_active_issues). Not tied to
    models.Notification - that table is still populated separately by the
    arr_health check type for its own richer wiki-linked alerts."""

    service_id: int
    service_name: str
    service_type: str
    icon_type: str | None = None
    icon_value: str | None = None
    check_name: str
    check_type: str
    status: str
    message: str
    timestamp: datetime


class ServiceStatusOut(BaseModel):
    service: ServiceOut
    overall_status: str
    last_checked: datetime | None
    latest_results: list[CheckResultOut]
    active_notification_count: int


class IconUploadOut(BaseModel):
    filename: str
    url: str


class ConnectionTestRequest(BaseModel):
    type: str
    local_url: str | None = None
    remote_url: str | None = None
    api_key: str | None = None
    api_key_env_var: str | None = None
    username: str | None = None


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str


class ConnectionTestResponse(BaseModel):
    local: ConnectionTestResult | None = None
    remote: ConnectionTestResult | None = None


class PlexAuthStartResponse(BaseModel):
    pin_id: int
    code: str
    auth_url: str


class PlexAuthPollResponse(BaseModel):
    token: str | None = None


class LibraryScanResponse(BaseModel):
    checks_created: list[CheckDefinitionOut]
    paths_found: int


class CheckBulkUpdateItem(BaseModel):
    check_id: int
    enabled: bool | None = None
    config: dict[str, Any] | None = None


class CheckBulkUpdateRequest(BaseModel):
    updates: list[CheckBulkUpdateItem]


class CheckBulkUpdateResponse(BaseModel):
    updated: list[CheckDefinitionOut]
    skipped_ids: list[int] = Field(default_factory=list)


class DashboardLayoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    sizes: dict[str, Any]
    columns: int | None = None
    card_service_ids: list[int]
    is_default: bool
    is_active: bool
    is_compact: bool
    is_mobile: bool
    created_at: datetime
    updated_at: datetime


class DashboardLayoutSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_active: bool
    is_default: bool
    is_compact: bool
    is_mobile: bool


class DashboardLayoutCreate(BaseModel):
    name: str
    sizes: dict[str, Any] = Field(default_factory=dict)
    columns: int | None = None
    # None -> server defaults to every currently-configured service, a
    # sensible starting point for a brand new layout the user then trims.
    card_service_ids: list[int] | None = None
    is_compact: bool = False
    is_mobile: bool = False


class DashboardLayoutUpdate(BaseModel):
    # is_compact/is_mobile are deliberately not here - a layout is fixed
    # into one of the four (is_mobile, is_compact) pools at creation
    # (DashboardLayoutCreate), never flipped in place afterward, see
    # DashboardLayout's docstring.
    name: str | None = None
    sizes: dict[str, Any] | None = None
    columns: int | None = None
    card_service_ids: list[int] | None = None


class NotificationChannelBase(BaseModel):
    name: str
    type: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    notify_on_warn: bool = True
    notify_on_fail: bool = True


class NotificationChannelCreate(NotificationChannelBase):
    secret: str | None = None
    secret_use_env: bool | None = None
    secret_env_var: str | None = None


class NotificationChannelUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None
    notify_on_warn: bool | None = None
    notify_on_fail: bool | None = None
    secret: str | None = None
    clear_secret: bool = False
    secret_use_env: bool | None = None
    secret_env_var: str | None = None


class NotificationChannelOut(NotificationChannelBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    has_secret: bool
    secret_env_var: str | None = None
    created_at: datetime
    updated_at: datetime


class NotificationChannelTestResult(BaseModel):
    ok: bool
    message: str


RECURRENCE_TYPES = ["once", "daily", "weekly", "monthly", "yearly"]


class ServiceGroupBase(BaseModel):
    name: str


class ServiceGroupCreate(ServiceGroupBase):
    service_ids: list[int] = Field(default_factory=list)


class ServiceGroupUpdate(BaseModel):
    name: str | None = None
    service_ids: list[int] | None = None


class ServiceGroupOut(ServiceGroupBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_default: bool
    service_ids: list[int]
    created_at: datetime
    updated_at: datetime


class DowntimeScheduleBase(BaseModel):
    name: str
    recurrence: str
    start_at: datetime
    end_at: datetime
    repeat_until: date | None = None
    suppress_warn: bool = True
    suppress_fail: bool = True
    enabled: bool = True

    @model_validator(mode="after")
    def _validate(self):
        if self.recurrence not in RECURRENCE_TYPES:
            raise ValueError(f"Unknown recurrence '{self.recurrence}'")
        if not self.suppress_warn and not self.suppress_fail:
            raise ValueError("A schedule must suppress at least Warn or Fail")
        if self.end_at <= self.start_at:
            raise ValueError("End must be after start")
        return self


class DowntimeScheduleCreate(DowntimeScheduleBase):
    group_ids: list[int] = Field(default_factory=list)
    # Set only at creation, by the "Instantly start SDT" flow - never in
    # DowntimeScheduleUpdate, see DowntimeSchedule.is_instant's docstring.
    is_instant: bool = False


class DowntimeScheduleUpdate(BaseModel):
    name: str | None = None
    recurrence: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    repeat_until: date | None = None
    clear_repeat_until: bool = False
    suppress_warn: bool | None = None
    suppress_fail: bool | None = None
    enabled: bool | None = None
    group_ids: list[int] | None = None


class DowntimeScheduleOut(DowntimeScheduleBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    group_ids: list[int]
    is_instant: bool
    created_at: datetime
    updated_at: datetime


class LogPruningSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    retention_days: int
    last_pruned_at: datetime | None
    updated_at: datetime


class LogPruningSettingsUpdate(BaseModel):
    retention_days: int | None = Field(default=None, ge=1, le=3650)


class PruneNowResult(BaseModel):
    deleted: int


class DashboardSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    public_layout_id: int | None
    public_layout_id_mobile: int | None
    updated_at: datetime


class DashboardSettingsUpdate(BaseModel):
    public_layout_id: int | None = None
    clear_public_layout: bool = False
    public_layout_id_mobile: int | None = None
    clear_public_layout_mobile: bool = False
