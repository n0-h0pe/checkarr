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
    # dashboard-icons has no separate plain-rtorrent icon (only rutorrent.svg
    # exists in that set) - bare rTorrent and ruTorrent both use it.
    "rtorrent": f"{_ICON_BASE}/rutorrent.svg",
    "rutorrent": f"{_ICON_BASE}/rutorrent.svg",
    "overseerr": f"{_ICON_BASE}/overseerr.svg",
    "jellyseerr": f"{_ICON_BASE}/jellyseerr.svg",
    "immich": f"{_ICON_BASE}/immich.svg",
    "dispatcharr": f"{_ICON_BASE}/dispatcharr.svg",
    "sportarr": f"{_ICON_BASE}/sportarr.svg",
    # No svg in dashboard-icons for this one (yet) - it does have a png.
    "cleanuparr": "https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/cleanuparr.png",
}

# Used to autofill the Name field and the Local address placeholder when a
# type is picked in Add Service - "port" is each app's documented default,
# omitted where there isn't a real convention (rTorrent/ruTorrent have none;
# Chaptarr's isn't established).
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
    "rutorrent": {"name": "ruTorrent", "port": None},
    "overseerr": {"name": "Seerr", "port": 5055},
    "jellyseerr": {"name": "Jellyseerr", "port": 5055},
    "immich": {"name": "Immich", "port": 2283},
    "dispatcharr": {"name": "Dispatcharr", "port": 9191},
    "sportarr": {"name": "Sportarr", "port": None},
    "cleanuparr": {"name": "Cleanuparr", "port": None},
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
                "label": "Path in Checkarr container",
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
        "type": "arr_disk_space",
        "label": "Free disk space via API",
        "applies_to": ["radarr", "sonarr", "lidarr", "whisparr"],
        "fields": [
            {
                "key": "path",
                "label": "Path to check (optional, default: worst of every disk {service} reports on)",
                "kind": "text",
                "default": "",
            },
            {"key": "warn_percent", "label": "Warn below % free", "kind": "number", "default": 10},
            {"key": "fail_percent", "label": "Fail below % free", "kind": "number", "default": 3},
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
    {
        "type": "qbittorrent_disk_space",
        "label": "Free disk space via API",
        "applies_to": ["qbittorrent"],
        "fields": [
            {
                "key": "total_disk_gb",
                "label": "Total disk size (GB) - optional, enables the % thresholds below",
                "kind": "number",
                "default": None,
            },
            {"key": "warn_percent", "label": "Warn below % free", "kind": "number", "default": 10},
            {"key": "fail_percent", "label": "Fail below % free", "kind": "number", "default": 3},
        ],
    },
    {
        "type": "deluge_disk_space",
        "label": "Free disk space via API",
        "applies_to": ["deluge"],
        "fields": [
            {
                "key": "path",
                "label": "Path to check (optional, defaults to Deluge's download location)",
                "kind": "text",
                "default": "",
            },
            {
                "key": "total_disk_gb",
                "label": "Total disk size (GB) - optional, enables the % thresholds below",
                "kind": "number",
                "default": None,
            },
            {"key": "warn_percent", "label": "Warn below % free", "kind": "number", "default": 10},
            {"key": "fail_percent", "label": "Fail below % free", "kind": "number", "default": 3},
        ],
    },
    {
        "type": "rtorrent_rpc_status",
        "label": "XML-RPC endpoint reachable",
        "applies_to": ["rtorrent", "rutorrent"],
        "fields": [
            {
                "key": "rpc_path",
                "label": "URL Path to the XML-RPC endpoint",
                "kind": "text",
                "default": "/RPC2",
            },
        ],
    },
    {
        "type": "ftp_path",
        "label": "Path exists and is populated, via FTP/FTPS",
        "applies_to": SERVICE_TYPES,
        "fields": [
            {"key": "host", "label": "FTP host", "kind": "text", "default": ""},
            {"key": "port", "label": "Port", "kind": "number", "default": 21},
            {"key": "username", "label": "Username (optional, default: anonymous)", "kind": "text", "default": ""},
            {"key": "password", "label": "Password (optional)", "kind": "password", "default": ""},
            {"key": "path", "label": "Remote path to check", "kind": "text", "default": ""},
            {"key": "min_entries", "label": "Minimum entries expected", "kind": "number", "default": 1},
            {"key": "use_tls", "label": "Use FTPS (TLS)", "kind": "checkbox", "default": False},
        ],
    },
    {
        "type": "overseerr_status",
        "label": "API reachable (Status)",
        "applies_to": ["overseerr", "jellyseerr"],
        "fields": [],
    },
    {
        "type": "overseerr_tmdb_status",
        "label": "TMDB reachable (the movie/TV metadata API {service} depends on)",
        "applies_to": ["overseerr", "jellyseerr"],
        "fields": [],
    },
    {
        "type": "ssl_certificate",
        "label": "SSL certificate validity",
        "applies_to": SERVICE_TYPES,
        "fields": [
            {"key": "expiry_warn_days", "label": "Warn when expiring within (days)", "kind": "number", "default": 14},
        ],
    },
    {
        "type": "immich_server_status",
        "label": "API reachable (Server statistics)",
        "applies_to": ["immich"],
        "fields": [],
    },
    {
        "type": "immich_storage",
        "label": "Free disk space via API",
        "applies_to": ["immich"],
        "fields": [
            {"key": "warn_percent", "label": "Warn below % free", "kind": "number", "default": 10},
            {"key": "fail_percent", "label": "Fail below % free", "kind": "number", "default": 3},
        ],
    },
    {
        "type": "immich_jobs",
        "label": "Background job queues (failed job count)",
        "applies_to": ["immich"],
        "fields": [
            {"key": "warn_failed_jobs", "label": "Warn at this many failed jobs", "kind": "number", "default": 1},
        ],
    },
]

# Meta for Settings > Push Notifications channel types - same shape as
# CHECK_TYPE_META, and deliberately so: adding a new alerting service later
# (Ntfy, Gotify, ...) means one more entry here plus one new sender in
# app/notifiers/ and one entry in alerting.py's _SENDERS, no schema or UI
# redesign. A field flagged "secret": True is stored encrypted and never
# echoed back in plaintext - see NotificationChannel.secret_encrypted and
# the has_secret/"leave blank to keep existing" pattern already used for
# service API keys. NotificationChannel has exactly one such secret slot per
# channel, so every type below puts whichever field is the actual bearer
# credential (a webhook URL, a bot/app token) there, and any other,
# non-secret identifier (a chat ID, a user key) as a plain field instead.
# "info" is not a real input, just a rendered note with nothing to save -
# see renderChannelDynamicFields in app.js.
NOTIFICATION_CHANNEL_TYPE_META = [
    {
        "type": "email",
        "label": "Email (SMTP)",
        "fields": [
            {"key": "smtp_host", "label": "SMTP host", "kind": "text", "default": ""},
            {"key": "smtp_port", "label": "SMTP port", "kind": "number", "default": 587},
            {"key": "smtp_username", "label": "SMTP username (optional)", "kind": "text", "default": ""},
            {"key": "smtp_password", "label": "SMTP password (optional)", "kind": "password", "default": "", "secret": True},
            {"key": "use_tls", "label": "Use STARTTLS (port 465 always uses implicit TLS instead)", "kind": "checkbox", "default": True},
            {"key": "from_address", "label": "From address", "kind": "text", "default": ""},
            {"key": "to_addresses", "label": "To address(es) (comma separated)", "kind": "text", "default": ""},
        ],
    },
    {
        "type": "discord",
        "label": "Discord",
        "fields": [
            {
                "key": "webhook_url",
                "label": "Webhook URL (Server Settings > Integrations > Webhooks)",
                "kind": "password",
                "default": "",
                "secret": True,
            },
        ],
    },
    {
        "type": "slack",
        "label": "Slack",
        "fields": [
            {
                "key": "webhook_url",
                "label": "Incoming webhook URL",
                "kind": "password",
                "default": "",
                "secret": True,
            },
        ],
    },
    {
        "type": "telegram",
        "label": "Telegram",
        "fields": [
            {
                "key": "bot_token",
                "label": "Bot token (from @BotFather)",
                "kind": "password",
                "default": "",
                "secret": True,
            },
            {"key": "chat_id", "label": "Chat ID", "kind": "text", "default": ""},
        ],
    },
    {
        "type": "pushbullet",
        "label": "Pushbullet",
        "fields": [
            {
                "key": "access_token",
                "label": "Access token (Settings > Account > Create Access Token)",
                "kind": "password",
                "default": "",
                "secret": True,
            },
        ],
    },
    {
        "type": "pushover",
        "label": "Pushover",
        "fields": [
            {
                "key": "app_token",
                "label": "Application API token",
                "kind": "password",
                "default": "",
                "secret": True,
            },
            {"key": "user_key", "label": "User key", "kind": "text", "default": ""},
        ],
    },
    {
        "type": "webhook",
        "label": "Webhook (generic)",
        "fields": [
            {
                "key": "url",
                "label": 'URL to POST {"subject", "message"} to as JSON',
                "kind": "password",
                "default": "",
                "secret": True,
            },
        ],
    },
    {
        "type": "browser",
        "label": "Browser (notification in an open admin tab)",
        "fields": [
            {
                "key": "_info",
                "label": (
                    "Shows a native OS notification in any browser tab that has this "
                    "dashboard open and connected - no address or account to enter, "
                    "just this browser. Grant it permission below once you've saved "
                    "this channel; a closed tab never receives one."
                ),
                "kind": "info",
            },
        ],
    },
]


@router.get("")
def get_meta():
    return {
        "service_types": SERVICE_TYPES,
        "check_types": CHECK_TYPE_META,
        "service_type_icons": SERVICE_TYPE_ICONS,
        "service_type_defaults": SERVICE_TYPE_DEFAULTS,
        "notification_channel_types": NOTIFICATION_CHANNEL_TYPE_META,
        "build": {"version": VERSION, "build_date": BUILD_DATE},
    }
