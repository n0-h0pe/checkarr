from fastapi import APIRouter, Depends

from ..schemas import SERVICE_TYPES
from ..security import require_auth
from ..version import BUILD_DATE, VERSION

router = APIRouter(prefix="/api/meta", tags=["meta"], dependencies=[Depends(require_auth)])

_ICON_BASE = "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/svg"

# Real app logos (walkxcode/dashboard-icons, the icon set behind Homarr/
# Homepage) rather than emoji. "generic" has none on purpose - falls back to
# a plain glyph client-side rather than picking a mismatched real logo.
SERVICE_TYPE_ICONS = {
    "radarr": f"{_ICON_BASE}/radarr.svg",
    "sonarr": f"{_ICON_BASE}/sonarr.svg",
    "prowlarr": f"{_ICON_BASE}/prowlarr.svg",
    "lidarr": f"{_ICON_BASE}/lidarr.svg",
    "whisparr": f"{_ICON_BASE}/whisparr.svg",
    "chaptarr": f"{_ICON_BASE}/chaptarr.svg",
    "plex": f"{_ICON_BASE}/plex.svg",
    "jellyfin": f"{_ICON_BASE}/jellyfin.svg",
    "qbittorrent": f"{_ICON_BASE}/qbittorrent.svg",
    "deluge": f"{_ICON_BASE}/deluge.svg",
    "rtorrent": f"{_ICON_BASE}/rutorrent.svg",  # rTorrent has no web UI of its own - this is its usual ruTorrent frontend
}

# Used to autofill the Name field and the Local address placeholder when a
# type is picked in Add Service - "port" is each app's documented default,
# omitted where there isn't a real convention (rTorrent has no web UI of its
# own; Chaptarr's isn't established).
SERVICE_TYPE_DEFAULTS = {
    "radarr": {"name": "Radarr", "port": 7878},
    "sonarr": {"name": "Sonarr", "port": 8989},
    "prowlarr": {"name": "Prowlarr", "port": 9696},
    "lidarr": {"name": "Lidarr", "port": 8686},
    "whisparr": {"name": "Whisparr", "port": 6969},
    "chaptarr": {"name": "Chaptarr", "port": None},
    "plex": {"name": "Plex", "port": 32400},
    "jellyfin": {"name": "Jellyfin", "port": 8096},
    "qbittorrent": {"name": "qBittorrent", "port": 8080},
    "deluge": {"name": "Deluge", "port": 8112},
    "rtorrent": {"name": "rTorrent", "port": None},
    "generic": {"name": "", "port": None},
}

CHECK_TYPE_META = [
    {
        "type": "http_200",
        "label": "HTTP 200 (web UI reachable)",
        "applies_to": SERVICE_TYPES,
        "fields": [
            {"key": "path", "label": "Path (optional, default /)", "kind": "text", "default": ""},
            {"key": "method", "label": "HTTP method", "kind": "select", "options": ["GET", "HEAD"], "default": "GET"},
            {
                "key": "expected_status_codes",
                "label": "Expected status codes (comma separated)",
                "kind": "text",
                "default": "200",
            },
        ],
    },
    {
        "type": "keyword_match",
        "label": "Keyword in response body",
        "applies_to": SERVICE_TYPES,
        "fields": [
            {"key": "path", "label": "Path (optional, default /)", "kind": "text", "default": ""},
            {"key": "keyword", "label": "Keyword", "kind": "text", "default": ""},
            {
                "key": "mode",
                "label": "Mode",
                "kind": "select",
                "options": ["must_contain", "must_not_contain"],
                "default": "must_contain",
            },
        ],
    },
    {
        "type": "filesystem_path",
        "label": "Filesystem path check via bind mount (for services with no browse API)",
        "applies_to": SERVICE_TYPES,
        "fields": [
            {
                "key": "healthchecker_path",
                "label": "Path in HealthChecker container",
                "kind": "text",
                "default": "",
            },
            {
                "key": "service_path",
                "label": "Path in {service} container (optional, for reference only)",
                "kind": "text",
                "default": "",
            },
            {"key": "min_entries", "label": "Minimum entries expected", "kind": "number", "default": 1},
        ],
    },
    {
        "type": "arr_system_status",
        "label": "API reachable (System Status)",
        "applies_to": ["radarr", "sonarr", "prowlarr", "lidarr", "whisparr"],
        "fields": [],
    },
    {
        "type": "arr_root_folder",
        "label": "Root folders accessible and populated (detects unmounted/empty drives)",
        "applies_to": ["radarr", "sonarr", "lidarr", "whisparr"],
        "fields": [
            {
                "key": "min_free_bytes",
                "label": "Warn below free space (bytes, optional)",
                "kind": "number",
                "default": None,
            }
        ],
    },
    {
        "type": "arr_filesystem_path",
        "label": "Filesystem path check via API (no volume mount needed)",
        "applies_to": ["radarr", "sonarr", "lidarr", "whisparr"],
        "fields": [
            {"key": "path", "label": "Path in {service} container", "kind": "text", "default": ""},
            {"key": "min_entries", "label": "Minimum entries expected", "kind": "number", "default": 1},
        ],
    },
    {
        "type": "arr_health",
        "label": "System health / notifications feed",
        "applies_to": ["radarr", "sonarr", "prowlarr", "lidarr", "whisparr"],
        "fields": [],
    },
    {
        "type": "plex_identity",
        "label": "Plex identity endpoint",
        "applies_to": ["plex"],
        "fields": [],
    },
    {
        "type": "plex_remote_access",
        "label": "Remote Access status (plex.tv + plex.direct reachability)",
        "applies_to": ["plex"],
        "fields": [
            {
                "key": "client_identifier",
                "label": "Plex server client identifier (optional, disambiguates multiple servers on one account)",
                "kind": "text",
                "default": "",
            },
        ],
    },
    {
        "type": "plex_filesystem_path",
        "label": "Filesystem path check via API (no volume mount needed)",
        "applies_to": ["plex"],
        "fields": [
            {"key": "path", "label": "Path in {service} container", "kind": "text", "default": ""},
            {"key": "min_entries", "label": "Minimum entries expected", "kind": "number", "default": 1},
            {
                "key": "fail_severity",
                "label": "Status when empty",
                "kind": "select",
                "options": ["fail", "warn"],
                "default": "fail",
            },
        ],
    },
    {
        "type": "jellyfin_health",
        "label": "Jellyfin /health endpoint",
        "applies_to": ["jellyfin"],
        "fields": [],
    },
    {
        "type": "jellyfin_filesystem_path",
        "label": "Filesystem path check via API (no volume mount needed)",
        "applies_to": ["jellyfin"],
        "fields": [
            {"key": "path", "label": "Path in {service} container", "kind": "text", "default": ""},
            {"key": "min_entries", "label": "Minimum entries expected", "kind": "number", "default": 1},
            {
                "key": "fail_severity",
                "label": "Status when empty",
                "kind": "select",
                "options": ["fail", "warn"],
                "default": "fail",
            },
        ],
    },
    {
        "type": "qbittorrent_login",
        "label": "Login via API (verifies configured username/password)",
        "applies_to": ["qbittorrent"],
        "fields": [],
    },
    {
        "type": "deluge_login",
        "label": "Login via API (verifies configured password)",
        "applies_to": ["deluge"],
        "fields": [],
    },
]


@router.get("")
def get_meta():
    return {
        "service_types": SERVICE_TYPES,
        "check_types": CHECK_TYPE_META,
        "service_type_icons": SERVICE_TYPE_ICONS,
        "service_type_defaults": SERVICE_TYPE_DEFAULTS,
        "build": {"version": VERSION, "build_date": BUILD_DATE},
    }
