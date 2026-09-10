from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SERVICE_TYPES = ["radarr", "sonarr", "prowlarr", "plex", "jellyfin", "generic"]
CHECK_TYPES = [
    "http_200",
    "keyword_match",
    "filesystem_path",
    "arr_system_status",
    "arr_root_folder",
    "arr_health",
    "plex_identity",
    "jellyfin_health",
]


class CheckDefinitionBase(BaseModel):
    name: str
    type: str
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class CheckDefinitionCreate(CheckDefinitionBase):
    pass


class CheckDefinitionUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class CheckDefinitionOut(CheckDefinitionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    service_id: int
    is_builtin: bool


class ServiceBase(BaseModel):
    name: str
    type: str
    base_url: str
    verify_ssl: bool = True
    enabled: bool = True
    poll_interval_seconds: int | None = None
    notes: str | None = None


class ServiceCreate(ServiceBase):
    api_key: str | None = None


class ServiceUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
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
