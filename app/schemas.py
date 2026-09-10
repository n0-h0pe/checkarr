from datetime import datetime
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
    "generic",
]
CHECK_TYPES = [
    "http_200",
    "keyword_match",
    "filesystem_path",
    "arr_system_status",
    "arr_root_folder",
    "arr_health",
    "arr_filesystem_path",
    "plex_identity",
    "plex_remote_access",
    "jellyfin_health",
]


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


class ServiceBase(BaseModel):
    name: str
    type: str
    local_url: str | None = None
    remote_url: str | None = None
    check_both_targets: bool = False
    verify_ssl: bool = True
    enabled: bool = True
    poll_interval_seconds: int | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _require_an_address(self):
        if not self.local_url and not self.remote_url:
            raise ValueError("At least one of local_url or remote_url must be set")
        return self


class ServiceCreate(ServiceBase):
    api_key: str | None = None


class ServiceUpdate(BaseModel):
    name: str | None = None
    local_url: str | None = None
    remote_url: str | None = None
    clear_local_url: bool = False
    clear_remote_url: bool = False
    check_both_targets: bool | None = None
    api_key: str | None = None
    clear_api_key: bool = False
    verify_ssl: bool | None = None
    enabled: bool | None = None
    poll_interval_seconds: int | None = None
    notes: str | None = None


class ServiceOut(ServiceBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    has_api_key: bool
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


class ServiceStatusOut(BaseModel):
    service: ServiceOut
    overall_status: str
    last_checked: datetime | None
    latest_results: list[CheckResultOut]
    active_notification_count: int
