import time
from datetime import datetime

import httpx

from .base import STATUS_FAIL, STATUS_OK, STATUS_WARN, CheckOutcome, NotificationItem, build_headers, humanize_bytes

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


async def check_arr_disk_space(
    client: httpx.AsyncClient, base_url: str, api_key: str | None, service_type: str, config: dict
) -> CheckOutcome:
    """Free disk space via the app's own dedicated /diskspace API - unlike
    /rootfolder (which check_root_folders above reads for its absolute-bytes
    threshold), this endpoint reports both free AND total capacity per
    monitored mount, so percentage thresholds work directly from the API
    with nothing to fill in manually (unlike the torrent client disk-space
    checks, whose APIs only ever report free bytes).

    Checks every disk the app reports on and flags the worst one, unless
    `path` narrows it to a single mount - same "just works with no config"
    default as the built-in Root folders accessible check.
    """
    path_filter = (config.get("path") or "").strip() or None
    warn_percent = config.get("warn_percent", 10)
    fail_percent = config.get("fail_percent", 3)

    url = base_url.rstrip("/") + _api_base(service_type) + "/diskspace"
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
        return CheckOutcome(STATUS_FAIL, f"Disk space API returned HTTP {resp.status_code}", elapsed)

    try:
        entries = resp.json()
    except ValueError:
        return CheckOutcome(STATUS_FAIL, "Disk space API returned invalid JSON", elapsed)

    if path_filter:
        entries = [e for e in entries if e.get("path") == path_filter]
        if not entries:
            return CheckOutcome(STATUS_FAIL, f"No disk space entry found for path '{path_filter}'", elapsed)
    if not entries:
        return CheckOutcome(STATUS_WARN, "No monitored disks reported", elapsed)

    worst, worst_percent = None, None
    for e in entries:
        total = e.get("totalSpace") or 0
        percent = (e.get("freeSpace") or 0) / total * 100 if total else 100.0
        if worst_percent is None or percent < worst_percent:
            worst, worst_percent = e, percent

    free_str = humanize_bytes(worst.get("freeSpace") or 0)
    total_str = humanize_bytes(worst.get("totalSpace") or 0)
    label = worst.get("path") or worst.get("label") or "disk"
    worst_of = f" (worst of {len(entries)} monitored disks)" if len(entries) > 1 else ""

    if worst_percent < fail_percent:
        status = STATUS_FAIL
    elif worst_percent < warn_percent:
        status = STATUS_WARN
    else:
        status = STATUS_OK
    return CheckOutcome(
        status, f"{label}: {free_str} free ({worst_percent:.1f}% of {total_str}){worst_of}", elapsed
    )


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
    # The actual text Radarr/Sonarr would show in their own UI (e.g. "Indexer
    # X is unavailable"), not just a bare count - this is what ends up as
    # this check's CheckResult.message, so it's what shows on the dashboard
    # card, the Notifications tab (queries.get_active_issues reads the
    # latest failing CheckResult, not the separate Notification table below),
    # and the History log. A bare "N active health issue(s) reported" told
    # you *that* something was wrong, never *what*, without switching over
    # to the target app itself to find out.
    if len(notifications) == 1:
        message = notifications[0].message
    else:
        message = f"{len(notifications)} active health issues: " + "; ".join(n.message for n in notifications)
    return CheckOutcome(status, message, elapsed, notifications=notifications)


# Wanted > Missing is paged; this many records per request, and at most this
# many requests per poll - 20k missing items is far past any real library,
# and the cap keeps one huge one from turning every poll into a long crawl.
_MISSING_PAGE_SIZE = 1000
_MISSING_MAX_PAGES = 20
_MISSING_NAMES_SHOWN = 5


def _parse_api_time(value) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _missing_item(record: dict, now: float) -> tuple[str, str] | None:
    """(stable key, display label) for one Wanted > Missing record, or None
    for one that can't actually have a file yet - an episode that hasn't
    aired, an album not released, a movie Radarr doesn't consider available
    yet. Radarr's own missing list doesn't filter those out, and an item
    that was never obtainable isn't a missing file, it's just waiting.

    Shape-based rather than per service type, so Whisparr works whichever
    base it's on (v2 is a Sonarr fork - episodes; v3 a Radarr fork - movies)."""
    rec_id = record.get("id")
    if rec_id is None:
        return None
    if "episodeNumber" in record:
        aired = _parse_api_time(record.get("airDateUtc"))
        if aired is None or aired > now:
            return None
        series = (record.get("series") or {}).get("title") or f"Series #{record.get('seriesId', '?')}"
        season, episode = record.get("seasonNumber") or 0, record.get("episodeNumber") or 0
        return f"episode:{rec_id}", f"{series} S{season:02d}E{episode:02d}"
    if "artistId" in record or "artist" in record:
        released = _parse_api_time(record.get("releaseDate"))
        if released is not None and released > now:
            return None
        artist = (record.get("artist") or {}).get("artistName") or "Unknown artist"
        return f"album:{rec_id}", f"{artist} - {record.get('title') or 'Unknown album'}"
    if record.get("isAvailable") is False or record.get("hasFile"):
        return None
    year = record.get("year")
    title = record.get("title") or f"Movie #{rec_id}"
    return f"movie:{rec_id}", f"{title} ({year})" if year else title


async def _fetch_missing_records(
    client: httpx.AsyncClient, base_url: str, api_key: str | None, service_type: str
) -> tuple[list[dict], bool] | str:
    """Every monitored record on the app's Wanted > Missing list, plus
    whether the page cap cut it short - or an error message. Radarr versions
    from before it had a Wanted page 404 here, so those fall back to the
    full movie list, filtered the same way that page would be."""
    api = base_url.rstrip("/") + _api_base(service_type)
    headers = build_headers(api_key)
    params = {
        "pageSize": _MISSING_PAGE_SIZE,
        "monitored": "true",
        "includeSeries": "true",
        "includeArtist": "true",
    }
    records: list[dict] = []
    for page in range(1, _MISSING_MAX_PAGES + 1):
        try:
            resp = await client.get(api + "/wanted/missing", headers=headers, params={**params, "page": page})
        except httpx.RequestError as exc:
            return f"API request to {api}/wanted/missing failed: {exc}"
        if resp.status_code == 401:
            return "API key rejected (HTTP 401)"
        if resp.status_code == 404 and page == 1 and service_type in ("radarr", "whisparr"):
            return await _fetch_missing_movies_fallback(client, api, headers)
        if resp.status_code != 200:
            return f"Wanted/missing API returned HTTP {resp.status_code}"
        try:
            data = resp.json()
        except ValueError:
            return "Wanted/missing API returned invalid JSON"
        page_records = data.get("records") or []
        records.extend(page_records)
        total = data.get("totalRecords") or 0
        if len(page_records) < _MISSING_PAGE_SIZE or len(records) >= total:
            return records, False
    return records, True


async def _fetch_missing_movies_fallback(
    client: httpx.AsyncClient, api: str, headers: dict
) -> tuple[list[dict], bool] | str:
    try:
        resp = await client.get(api + "/movie", headers=headers)
    except httpx.RequestError as exc:
        return f"API request to {api}/movie failed: {exc}"
    if resp.status_code != 200:
        return f"Movie API returned HTTP {resp.status_code}"
    try:
        movies = resp.json()
    except ValueError:
        return "Movie API returned invalid JSON"
    return [m for m in movies if m.get("monitored") and not m.get("hasFile")], False


async def check_missing_files(
    client: httpx.AsyncClient, base_url: str, api_key: str | None, service_type: str, config: dict, state: dict
) -> CheckOutcome:
    """Watches the app's Wanted > Missing list and reports anything that's
    stayed on it longer than `grace_minutes` (default 30) - long enough for
    a normal grab/import to finish, so a new episode that's downloading
    right now doesn't count, but a file that's disappeared from disk (or a
    download that never completed) does.

    `state` (CheckState.data, loaded and saved around this call by
    runner.run_check) remembers when each item was first seen missing,
    since the API only says what's missing now, not since when. The
    first-ever poll records everything already on the list as a baseline
    and never alerts on those - a library with years of never-found
    episodes would otherwise just sit at "warn" forever - unless
    `include_existing` is set. A baseline item that later gets a file and
    then goes missing again counts as new.

    Reports FAIL once anything is overdue; the check's own Alert level
    (config.alert_level, "warn" for the built-in one) is what turns that
    into a WARN instead - see poller.py."""
    grace_minutes = config.get("grace_minutes")
    grace_seconds = max(0.0, float(30 if grace_minutes is None else grace_minutes)) * 60
    include_existing = bool(config.get("include_existing"))

    start = time.perf_counter()
    fetched = await _fetch_missing_records(client, base_url, api_key, service_type)
    elapsed = (time.perf_counter() - start) * 1000
    if isinstance(fetched, str):
        # State deliberately left untouched - an outage mustn't reset how
        # long everything's been missing.
        return CheckOutcome(STATUS_FAIL, fetched, elapsed)
    records, truncated = fetched

    now = time.time()
    current: dict[str, str] = {}
    for record in records:
        item = _missing_item(record, now)
        if item:
            current[item[0]] = item[1]

    first_run = not state.get("initialized")
    seen = state.get("items") or {}
    # [first_seen_epoch, is_baseline] per key - labels aren't stored, since
    # the only ones ever shown are for items on the list right now. Anything
    # that's left the list is dropped, so it counts as new if it comes back.
    items = {key: seen.get(key) or [int(now), first_run] for key in current}
    state["items"] = items
    state["initialized"] = True

    overdue = sorted(
        (first_seen, current[key])
        for key, (first_seen, baseline) in items.items()
        if (include_existing or not baseline) and now - first_seen >= grace_seconds
    )
    baseline_count = sum(1 for _, baseline in items.values() if baseline)
    waiting = sum(
        1 for first_seen, baseline in items.values() if not baseline and now - first_seen < grace_seconds
    )
    # Kept short - this is what a dashboard card's check row shows, where a
    # long message crowds out the check's own name.
    grace_label = f"{grace_seconds / 60:g} min"
    suffix = f" (first {len(records)} checked)" if truncated else ""

    if overdue:
        names = [label for _, label in overdue[:_MISSING_NAMES_SHOWN]]
        more = f" and {len(overdue) - len(names)} more" if len(overdue) > len(names) else ""
        return CheckOutcome(
            STATUS_FAIL, f"{len(overdue)} missing over {grace_label}: {', '.join(names)}{more}{suffix}", elapsed
        )
    if first_run and items:
        return CheckOutcome(STATUS_OK, f"Watching - {len(items)} already missing, not alerted on{suffix}", elapsed)
    if waiting:
        return CheckOutcome(STATUS_OK, f"{waiting} newly missing, under {grace_label}{suffix}", elapsed)
    if baseline_count and not include_existing:
        return CheckOutcome(STATUS_OK, f"No new missing files ({baseline_count} older ignored){suffix}", elapsed)
    return CheckOutcome(STATUS_OK, f"No missing files{suffix}", elapsed)
