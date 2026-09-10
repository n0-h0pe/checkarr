from fastapi import APIRouter, Depends

from ..schemas import SERVICE_TYPES
from ..security import require_auth

router = APIRouter(prefix="/api/meta", tags=["meta"], dependencies=[Depends(require_auth)])

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
        "label": "Filesystem path check (requires volume mount)",
        "applies_to": SERVICE_TYPES,
        "fields": [
            {"key": "path", "label": "Path inside this container", "kind": "text", "default": ""},
            {"key": "min_entries", "label": "Minimum entries expected", "kind": "number", "default": 1},
        ],
    },
    {
        "type": "arr_system_status",
        "label": "API reachable (System Status)",
        "applies_to": ["radarr", "sonarr", "prowlarr"],
        "fields": [],
    },
    {
        "type": "arr_root_folder",
        "label": "Root folders accessible (detects unmounted drives)",
        "applies_to": ["radarr", "sonarr"],
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
        "type": "arr_health",
        "label": "System health / notifications feed",
        "applies_to": ["radarr", "sonarr", "prowlarr"],
        "fields": [],
    },
    {
        "type": "plex_identity",
        "label": "Plex identity endpoint",
        "applies_to": ["plex"],
        "fields": [],
    },
    {
        "type": "jellyfin_health",
        "label": "Jellyfin /health endpoint",
        "applies_to": ["jellyfin"],
        "fields": [],
    },
]


@router.get("")
def get_meta():
    return {"service_types": SERVICE_TYPES, "check_types": CHECK_TYPE_META}
