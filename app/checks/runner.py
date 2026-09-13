import httpx

from ..models import CheckDefinition, Service
from ..security import resolve_secret
from .base import STATUS_FAIL, CheckOutcome
from .arr_check import (
    check_arr_disk_space,
    check_filesystem_path_api,
    check_health,
    check_root_folders,
    check_system_status,
)
from .filesystem_check import check_filesystem_path
from .ftp_check import check_ftp_path
from .http_check import check_http_200, check_keyword_match
from .immich_check import check_immich_jobs, check_immich_server_status, check_immich_storage
from .media_server_check import (
    check_jellyfin_filesystem_path,
    check_jellyfin_health,
    check_plex_filesystem_path,
    check_plex_identity,
    check_plex_remote_access,
)
from .overseerr_check import check_overseerr_status, check_overseerr_tmdb_status
from .port_check import check_external_port_open
from .ssl_check import check_ssl_certificate
from .torrent_client_check import (
    check_deluge_disk_space,
    check_deluge_login,
    check_qbittorrent_disk_space,
    check_qbittorrent_login,
    check_rtorrent_rpc_status,
)

ARR_TYPES = {"radarr", "sonarr", "prowlarr", "lidarr", "whisparr"}
ROOT_FOLDER_TYPES = {"radarr", "sonarr", "lidarr", "whisparr"}
OVERSEERR_TYPES = {"overseerr", "jellyseerr"}

# Checks that run once against a specific local/remote URL - the poller runs
# these once per configured target (local, remote, or both).
TARGET_SCOPED_TYPES = {
    "http_200",
    "keyword_match",
    "arr_system_status",
    "arr_root_folder",
    "arr_disk_space",
    "arr_health",
    "arr_filesystem_path",
    "plex_identity",
    "plex_filesystem_path",
    "jellyfin_health",
    "jellyfin_filesystem_path",
    "qbittorrent_login",
    "deluge_login",
    "qbittorrent_disk_space",
    "deluge_disk_space",
    "rtorrent_rpc_status",
    "overseerr_status",
    "overseerr_tmdb_status",
    "ssl_certificate",
    "immich_server_status",
    "immich_storage",
    "immich_jobs",
}

# Checks that don't care which URL is configured - the poller runs these
# exactly once per poll regardless of how many targets are set.
SERVICE_SCOPED_TYPES = {"filesystem_path", "plex_remote_access", "ftp_path", "external_port_open"}

# When a service has both a local and a remote address but hasn't opted into
# "run all checks against both", these target-scoped types still run against
# both addresses by default - everything else in TARGET_SCOPED_TYPES runs
# against local only. Reachability of the public/remote entry point is
# useful to know even when you don't want to double up on API-heavy checks.
# (ssl_certificate isn't here - it has its own https-only target selection
# in poller.py, since "both" doesn't make sense for a check that's not
# meaningful against a non-https address in the first place.)
ALWAYS_BOTH_TARGETS_TYPES = {"http_200"}


async def run_check(
    client: httpx.AsyncClient, service: Service, check: CheckDefinition, base_url: str | None
) -> CheckOutcome:
    api_key = resolve_secret(service.api_key_env_var, service.api_key_encrypted)
    config = check.config or {}
    ctype = check.type

    # Basic auth for services that gate their web UI behind htaccess-style
    # login (mainly rTorrent/ruTorrent, which has no API of its own) -
    # applied whenever both a username and a secret are configured,
    # regardless of type, since it's harmless for services that don't need it.
    basic_auth = (service.username, api_key) if service.username and api_key else None

    try:
        if ctype == "http_200":
            return await check_http_200(client, base_url, config, auth=basic_auth)
        if ctype == "keyword_match":
            return await check_keyword_match(client, base_url, config, auth=basic_auth)
        if ctype == "filesystem_path":
            return await check_filesystem_path(config)
        if ctype == "ftp_path":
            return await check_ftp_path(config)
        if ctype == "external_port_open":
            return await check_external_port_open(config)
        if ctype == "arr_system_status":
            return await check_system_status(client, base_url, api_key, service.type, config)
        if ctype == "arr_root_folder":
            return await check_root_folders(client, base_url, api_key, service.type, config)
        if ctype == "arr_disk_space":
            return await check_arr_disk_space(client, base_url, api_key, service.type, config)
        if ctype == "arr_health":
            return await check_health(client, base_url, api_key, service.type, config)
        if ctype == "arr_filesystem_path":
            return await check_filesystem_path_api(client, base_url, api_key, service.type, config)
        if ctype == "plex_identity":
            return await check_plex_identity(client, base_url, api_key, config)
        if ctype == "plex_filesystem_path":
            return await check_plex_filesystem_path(client, base_url, api_key, config)
        if ctype == "jellyfin_health":
            return await check_jellyfin_health(client, base_url, api_key, config)
        if ctype == "jellyfin_filesystem_path":
            jellyfin_admin_password = resolve_secret(service.jellyfin_admin_password_env_var, service.jellyfin_admin_password_encrypted)
            return await check_jellyfin_filesystem_path(
                client, base_url, api_key, config, service.username, jellyfin_admin_password
            )
        if ctype == "plex_remote_access":
            return await check_plex_remote_access(client, api_key, config)
        if ctype == "qbittorrent_login":
            return await check_qbittorrent_login(client, base_url, service.username, api_key, config)
        if ctype == "deluge_login":
            return await check_deluge_login(client, base_url, api_key, config)
        if ctype == "qbittorrent_disk_space":
            return await check_qbittorrent_disk_space(client, base_url, service.username, api_key, config)
        if ctype == "deluge_disk_space":
            return await check_deluge_disk_space(client, base_url, api_key, config)
        if ctype == "rtorrent_rpc_status":
            return await check_rtorrent_rpc_status(client, base_url, config, auth=basic_auth)
        if ctype == "overseerr_status":
            return await check_overseerr_status(client, base_url, api_key, config)
        if ctype == "overseerr_tmdb_status":
            return await check_overseerr_tmdb_status(client, base_url, api_key, config)
        if ctype == "ssl_certificate":
            return await check_ssl_certificate(base_url, config)
        if ctype == "immich_server_status":
            return await check_immich_server_status(client, base_url, api_key, config)
        if ctype == "immich_storage":
            return await check_immich_storage(client, base_url, api_key, config)
        if ctype == "immich_jobs":
            return await check_immich_jobs(client, base_url, api_key, config)
        return CheckOutcome(STATUS_FAIL, f"Unknown check type '{ctype}'", None)
    except Exception as exc:  # noqa: BLE001 - a broken check must not kill the poll loop
        return CheckOutcome(STATUS_FAIL, f"Check raised an unexpected error: {exc}", None)


def default_checks_for_service_type(service_type: str) -> list[dict]:
    """Sensible built-in checks pre-populated when a service is created."""
    checks = []
    # Bare rTorrent has no web UI or API of its own at all - only ruTorrent
    # (or something else fronting it) does, so "rtorrent" (bare) skips this
    # default entirely rather than seeding a check against nothing.
    if service_type != "rtorrent":
        if service_type == "plex":
            web_ui_config = {"path": "/web/index.html"}
        elif service_type == "rutorrent":
            web_ui_config = {"path": "/rutorrent/"}
        else:
            web_ui_config = {}
        checks.append({"name": "Web UI reachable", "type": "http_200", "config": web_ui_config, "is_builtin": True})
    if service_type in ARR_TYPES:
        checks += [
            {"name": "API status", "type": "arr_system_status", "config": {}, "is_builtin": True},
            {"name": "System health / notifications", "type": "arr_health", "config": {}, "is_builtin": True},
        ]
    if service_type in ROOT_FOLDER_TYPES:
        checks.append(
            {"name": "Root folders accessible", "type": "arr_root_folder", "config": {}, "is_builtin": True}
        )
        checks.append(
            {"name": "Free disk space", "type": "arr_disk_space", "config": {}, "is_builtin": True}
        )
    if service_type == "plex":
        checks.append({"name": "Plex identity", "type": "plex_identity", "config": {}, "is_builtin": True})
        checks.append(
            {
                "name": "Remote Access (plex.direct)",
                "type": "plex_remote_access",
                "config": {},
                "is_builtin": True,
                "interval_seconds": 600,
            }
        )
    if service_type == "jellyfin":
        checks.append({"name": "Jellyfin health", "type": "jellyfin_health", "config": {}, "is_builtin": True})
    if service_type == "qbittorrent":
        checks.append({"name": "Login (API)", "type": "qbittorrent_login", "config": {}, "is_builtin": True})
        checks.append({"name": "Free disk space", "type": "qbittorrent_disk_space", "config": {}, "is_builtin": True})
    if service_type == "deluge":
        checks.append({"name": "Login (API)", "type": "deluge_login", "config": {}, "is_builtin": True})
        checks.append({"name": "Free disk space", "type": "deluge_disk_space", "config": {}, "is_builtin": True})
    if service_type == "rtorrent":
        # config: {} -> falls back to /RPC2 (check_rtorrent_rpc_status), the
        # bare XML-RPC-over-HTTP bridge path with no ruTorrent in front.
        checks.append({"name": "XML-RPC reachable", "type": "rtorrent_rpc_status", "config": {}, "is_builtin": True})
    if service_type == "rutorrent":
        # ruTorrent's own httprpc plugin, the common case for a real
        # ruTorrent install (as opposed to a bare rTorrent RPC bridge) -
        # still editable per-service if a setup uses a different plugin/path.
        checks.append(
            {
                "name": "XML-RPC reachable",
                "type": "rtorrent_rpc_status",
                "config": {"rpc_path": "/rutorrent/plugins/httprpc/action.php"},
                "is_builtin": True,
            }
        )
    if service_type in OVERSEERR_TYPES:
        checks.append({"name": "API status", "type": "overseerr_status", "config": {}, "is_builtin": True})
        checks.append({"name": "TMDB reachable", "type": "overseerr_tmdb_status", "config": {}, "is_builtin": True})
    if service_type == "immich":
        checks.append({"name": "API status", "type": "immich_server_status", "config": {}, "is_builtin": True})
        checks.append({"name": "Free disk space", "type": "immich_storage", "config": {}, "is_builtin": True})
        checks.append({"name": "Background jobs", "type": "immich_jobs", "config": {}, "is_builtin": True})
    return checks
