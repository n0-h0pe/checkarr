import time

import httpx

from .base import STATUS_FAIL, STATUS_OK, STATUS_WARN, CheckOutcome, NotificationItem, build_headers

# Radarr/Sonarr speak the v3 Servarr API; Prowlarr speaks v1. Structurally identical.
API_PREFIX = {
    "radarr": "/api/v3",
    "sonarr": "/api/v3",
    "prowlarr": "/api/v1",
}


def _api_base(service_type: str) -> str:
    return API_PREFIX.get(service_type, "/api/v3")


async def check_system_status(
    client: httpx.AsyncClient, base_url: str, api_key: str | None, service_type: str, config: dict
) -> CheckOutcome:
    """Confirms the app itself (not just its reverse proxy/web UI) is up and the API key works."""
    url = base_url.rstrip("/") + _api_base(service_type) + "/system/status"
    start = time.perf_counter()
    try:
        resp = await client.get(url, headers=build_headers(api_key))
    except httpx.RequestError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"API request to {url} failed: {exc}", elapsed)
    elapsed = (time.perf_counter() - start) * 1000

    if resp.status_code == 401:
        return CheckOutcome(STATUS_FAIL, "API key rejected (HTTP 401) - check the configured key", elapsed)
    if resp.status_code != 200:
        return CheckOutcome(STATUS_FAIL, f"System status API returned HTTP {resp.status_code}", elapsed)

    try:
        data = resp.json()
        version = data.get("version", "unknown")
    except ValueError:
        version = "unknown"
    return CheckOutcome(STATUS_OK, f"API reachable, version {version}", elapsed)


async def check_root_folders(
    client: httpx.AsyncClient, base_url: str, api_key: str | None, service_type: str, config: dict
) -> CheckOutcome:
    """Uses Radarr/Sonarr's own root-folder accessibility flag to detect an unmounted/failed drive.

    This is the recommended way to detect a dead mount: Radarr/Sonarr report
    `accessible: false` for any root folder they can't see, which is exactly
    what happens when the underlying disk/network share fails to mount -
    without the health checker needing its own copy of the media volumes.
    """
    url = base_url.rstrip("/") + _api_base(service_type) + "/rootfolder"
    start = time.perf_counter()
    try:
        resp = await client.get(url, headers=build_headers(api_key))
    except httpx.RequestError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"API request to {url} failed: {exc}", elapsed)
    elapsed = (time.perf_counter() - start) * 1000

    if resp.status_code == 401:
        return CheckOutcome(STATUS_FAIL, "API key rejected (HTTP 401)", elapsed)
    if resp.status_code != 200:
        return CheckOutcome(STATUS_FAIL, f"Root folder API returned HTTP {resp.status_code}", elapsed)

    try:
        folders = resp.json()
    except ValueError:
        return CheckOutcome(STATUS_FAIL, "Root folder API returned invalid JSON", elapsed)

    if not folders:
        return CheckOutcome(STATUS_WARN, "No root folders configured", elapsed)

    min_free_bytes = config.get("min_free_bytes")
    bad, low_space = [], []
    for f in folders:
        path = f.get("path", "?")
        if not f.get("accessible", False):
            bad.append(path)
        elif min_free_bytes is not None and (f.get("freeSpace") or 0) < min_free_bytes:
            low_space.append(path)

    if bad:
        return CheckOutcome(
            STATUS_FAIL,
            f"Root folder(s) not accessible (likely unmounted/failed disk): {', '.join(bad)}",
            elapsed,
        )
    if low_space:
        return CheckOutcome(
            STATUS_WARN,
            f"Root folder(s) below free space threshold: {', '.join(low_space)}",
            elapsed,
        )
    return CheckOutcome(STATUS_OK, f"All {len(folders)} root folder(s) accessible", elapsed)


_SEVERITY_MAP = {"ok": "ok", "notice": "notice", "warning": "warning", "error": "error"}


async def check_health(
    client: httpx.AsyncClient, base_url: str, api_key: str | None, service_type: str, config: dict
) -> CheckOutcome:
    """Pulls the app's own System > Status health/notifications feed.

    This mirrors exactly what Radarr/Sonarr would show as a notification
    banner in their own UI (indexer down, missing files, low disk space,
    update available, etc.) so it can be consolidated into this dashboard.
    """
    url = base_url.rstrip("/") + _api_base(service_type) + "/health"
    start = time.perf_counter()
    try:
        resp = await client.get(url, headers=build_headers(api_key))
    except httpx.RequestError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"API request to {url} failed: {exc}", elapsed)
    elapsed = (time.perf_counter() - start) * 1000

    if resp.status_code == 401:
        return CheckOutcome(STATUS_FAIL, "API key rejected (HTTP 401)", elapsed)
    if resp.status_code != 200:
        return CheckOutcome(STATUS_FAIL, f"Health API returned HTTP {resp.status_code}", elapsed)

    try:
        items = resp.json()
    except ValueError:
        return CheckOutcome(STATUS_FAIL, "Health API returned invalid JSON", elapsed)

    notifications = [
        NotificationItem(
            source=f"{service_type}_health",
            severity=_SEVERITY_MAP.get((item.get("type") or "warning").lower(), "warning"),
            message=item.get("message", "Unspecified health issue"),
            wiki_url=item.get("wikiUrl"),
        )
        for item in items
    ]

    if not notifications:
        return CheckOutcome(STATUS_OK, "No active health issues reported", elapsed)

    worst = "error" if any(n.severity == "error" for n in notifications) else "warning"
    status = STATUS_FAIL if worst == "error" else STATUS_WARN
    return CheckOutcome(
        status,
        f"{len(notifications)} active health issue(s) reported",
        elapsed,
        notifications=notifications,
    )
