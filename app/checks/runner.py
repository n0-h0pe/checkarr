import httpx

from ..models import CheckDefinition, Service
from ..security import decrypt_secret
from .base import STATUS_FAIL, CheckOutcome
from .arr_check import check_health, check_root_folders, check_system_status
from .filesystem_check import check_filesystem_path
from .http_check import check_http_200, check_keyword_match
from .media_server_check import check_jellyfin_health, check_plex_identity

ARR_TYPES = {"radarr", "sonarr", "prowlarr"}


async def run_check(client: httpx.AsyncClient, service: Service, check: CheckDefinition) -> CheckOutcome:
    api_key = decrypt_secret(service.api_key_encrypted)
    config = check.config or {}
    ctype = check.type

    try:
        if ctype == "http_200":
            return await check_http_200(client, service.base_url, config)
        if ctype == "keyword_match":
            return await check_keyword_match(client, service.base_url, config)
        if ctype == "filesystem_path":
            return await check_filesystem_path(config)
        if ctype == "arr_system_status":
            return await check_system_status(client, service.base_url, api_key, service.type, config)
        if ctype == "arr_root_folder":
            return await check_root_folders(client, service.base_url, api_key, service.type, config)
        if ctype == "arr_health":
            return await check_health(client, service.base_url, api_key, service.type, config)
        if ctype == "plex_identity":
            return await check_plex_identity(client, service.base_url, api_key, config)
        if ctype == "jellyfin_health":
            return await check_jellyfin_health(client, service.base_url, api_key, config)
        return CheckOutcome(STATUS_FAIL, f"Unknown check type '{ctype}'", None)
    except Exception as exc:  # noqa: BLE001 - a broken check must not kill the poll loop
        return CheckOutcome(STATUS_FAIL, f"Check raised an unexpected error: {exc}", None)


def default_checks_for_service_type(service_type: str) -> list[dict]:
    """Sensible built-in checks pre-populated when a service is created."""
    checks = [
        {"name": "Web UI reachable", "type": "http_200", "config": {}, "is_builtin": True},
    ]
    if service_type in ARR_TYPES:
        checks += [
            {"name": "API status", "type": "arr_system_status", "config": {}, "is_builtin": True},
            {"name": "System health / notifications", "type": "arr_health", "config": {}, "is_builtin": True},
        ]
    if service_type in {"radarr", "sonarr"}:
        checks.append(
            {"name": "Root folders accessible", "type": "arr_root_folder", "config": {}, "is_builtin": True}
        )
    if service_type == "plex":
        checks.append({"name": "Plex identity", "type": "plex_identity", "config": {}, "is_builtin": True})
    if service_type == "jellyfin":
        checks.append({"name": "Jellyfin health", "type": "jellyfin_health", "config": {}, "is_builtin": True})
    return checks
