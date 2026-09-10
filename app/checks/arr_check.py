import time

import httpx

from .base import STATUS_FAIL, STATUS_OK, STATUS_WARN, CheckOutcome, NotificationItem, build_headers

# All Servarr-family apps expose a structurally identical REST API, just at
# different version prefixes. Radarr/Sonarr are on v3; Whisparr is a Radarr
# fork so shares v3. Prowlarr and Lidarr are still on v1.
API_PREFIX = {
    "radarr": "/api/v3",
    "sonarr": "/api/v3",
    "whisparr": "/api/v3",
    "prowlarr": "/api/v1",
    "lidarr": "/api/v1",
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


async def _browse_folder(
    client: httpx.AsyncClient, base_url: str, api_key: str | None, service_type: str, path: str
) -> tuple[int, int] | None:
    """Browses a path via the same filesystem API Radarr/Sonarr's own "Add
    Root Folder" folder picker uses (GET .../filesystem?path=...) - so
    directory contents are judged from the service's own point of view, not
    the health checker's, and no bind-mount is needed on this container at
    all. Works for any path the app can see, not just its configured root
    folders.

    Returns (directory_count, file_count), or None (inconclusive - never
    fails a check on its own) if the browse call itself errors; some very
    old Servarr versions may also lack this endpoint.
    """
    url = base_url.rstrip("/") + _api_base(service_type) + "/filesystem"
    try:
        resp = await client.get(
            url, headers=build_headers(api_key), params={"path": path, "includeFiles": "true"}
        )
    except httpx.RequestError:
        return None
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    directories = data.get("directories") or []
    files = data.get("files") or []
    return len(directories), len(files)


async def check_root_folders(
    client: httpx.AsyncClient, base_url: str, api_key: str | None, service_type: str, config: dict
) -> CheckOutcome:
    """Detects an unmounted/failed drive from two angles, both via the API
    (no bind-mounts needed):

    1. Radarr's/Sonarr's own root-folder `accessible` flag - catches a mount
       point that's outright gone.
    2. Actually browsing each accessible root folder's contents via the
       filesystem API - catches a mount point that's present but empty,
       e.g. an SMB share that mounted without populating. `accessible: true`
       alone does NOT catch this; that's exactly the gap this closes.
    """
    url = base_url.rstrip("/") + _api_base(service_type) + "/rootfolder"
    start = time.perf_counter()
    try:
        resp = await client.get(url, headers=build_headers(api_key))
    except httpx.RequestError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"API request to {url} failed: {exc}", elapsed)

    if resp.status_code == 401:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, "API key rejected (HTTP 401)", elapsed)
    if resp.status_code != 200:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"Root folder API returned HTTP {resp.status_code}", elapsed)

    try:
        folders = resp.json()
    except ValueError:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, "Root folder API returned invalid JSON", elapsed)

    if not folders:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_WARN, "No root folders configured", elapsed)

    min_free_bytes = config.get("min_free_bytes")
    bad, low_space, empty = [], [], []
    for f in folders:
        path = f.get("path", "?")
        if not f.get("accessible", False):
            bad.append(path)
            continue
        if min_free_bytes is not None and (f.get("freeSpace") or 0) < min_free_bytes:
            low_space.append(path)
        counts = await _browse_folder(client, base_url, api_key, service_type, path)
        if counts is not None and counts == (0, 0):
            empty.append(path)

    elapsed = (time.perf_counter() - start) * 1000

    if bad or empty:
        parts = []
        if bad:
            parts.append(f"not accessible (likely unmounted/failed disk): {', '.join(bad)}")
        if empty:
            parts.append(
                f"accessible but empty from {service_type}'s own view - possible failed/incomplete "
                f"mount underneath (e.g. an SMB share that mounted but didn't populate): {', '.join(empty)}"
            )
        return CheckOutcome(STATUS_FAIL, "Root folder(s) " + "; ".join(parts), elapsed)
    if low_space:
        return CheckOutcome(
            STATUS_WARN,
            f"Root folder(s) below free space threshold: {', '.join(low_space)}",
            elapsed,
        )
    return CheckOutcome(STATUS_OK, f"All {len(folders)} root folder(s) accessible and populated", elapsed)


async def check_filesystem_path_api(
    client: httpx.AsyncClient, base_url: str, api_key: str | None, service_type: str, config: dict
) -> CheckOutcome:
    """Checks any path exists and is non-empty using the target app's own
    filesystem-browse API - the same one its "Add Root Folder" picker uses.

    Unlike the generic `filesystem_path` check, this needs only a path as
    Radarr/Sonarr/etc. themselves see it: no bind-mount on the Checkarr
    container at all, because the app is doing the looking, not us. Use this
    for a path that isn't one of the app's configured root folders (those
    are already covered by the "Root folders accessible" check) - e.g. a
    specific subfolder you want to keep an eye on independently.
    """
    path = config.get("path")
    min_entries = config.get("min_entries", 1)
    if not path:
        return CheckOutcome(STATUS_FAIL, f"No 'Path in {service_type} container' configured", None)

    start = time.perf_counter()
    counts = await _browse_folder(client, base_url, api_key, service_type, path)
    elapsed = (time.perf_counter() - start) * 1000

    if counts is None:
        return CheckOutcome(
            STATUS_FAIL,
            f"Could not browse {path} via {service_type}'s API - check the path exists and the API key is valid",
            elapsed,
        )

    directories, files = counts
    total = directories + files
    if total < min_entries:
        return CheckOutcome(
            STATUS_FAIL,
            f"{path} has only {directories} folder(s) and {files} file(s) - possible unmounted/failed drive",
            elapsed,
        )
    return CheckOutcome(STATUS_OK, f"{path} accessible with {directories} folder(s) and {files} file(s)", elapsed)


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
