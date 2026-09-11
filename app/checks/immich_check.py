import time

import httpx

from .base import STATUS_FAIL, STATUS_OK, STATUS_WARN, CheckOutcome, build_headers, humanize_bytes

API_PREFIX = "/api"


async def check_immich_server_status(
    client: httpx.AsyncClient, base_url: str, api_key: str | None, config: dict
) -> CheckOutcome:
    """Confirms the app itself (not just its reverse proxy/web UI) is up and
    the API key works - GET /api/server/statistics, which (unlike the
    unauthenticated /api/server/ping) requires a valid key to answer, the
    same call Immich's own admin dashboard makes for its library counts."""
    url = base_url.rstrip("/") + API_PREFIX + "/server/statistics"
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
        return CheckOutcome(STATUS_FAIL, f"Statistics API returned HTTP {resp.status_code}", elapsed)

    try:
        data = resp.json()
    except ValueError:
        return CheckOutcome(STATUS_OK, "API reachable", elapsed)

    photos = data.get("photos")
    videos = data.get("videos")
    if photos is None and videos is None:
        return CheckOutcome(STATUS_OK, "API reachable", elapsed)
    return CheckOutcome(STATUS_OK, f"API reachable - {photos or 0} photo(s), {videos or 0} video(s)", elapsed)


async def check_immich_storage(
    client: httpx.AsyncClient, base_url: str, api_key: str | None, config: dict
) -> CheckOutcome:
    """Free space on Immich's own storage volume - GET /api/server/storage,
    the same figures shown on Immich's admin "Server Stats" page. Thresholds
    are % free, same convention as the qBittorrent/Deluge disk-space checks."""
    warn_percent = config.get("warn_percent", 10)
    fail_percent = config.get("fail_percent", 3)

    url = base_url.rstrip("/") + API_PREFIX + "/server/storage"
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
        return CheckOutcome(STATUS_FAIL, f"Storage API returned HTTP {resp.status_code}", elapsed)

    try:
        data = resp.json()
    except ValueError:
        return CheckOutcome(STATUS_OK, "API reachable, storage figures unavailable", elapsed)

    available_raw = data.get("diskAvailableRaw")
    size_raw = data.get("diskSizeRaw")
    if not isinstance(available_raw, (int, float)) or not isinstance(size_raw, (int, float)) or size_raw <= 0:
        return CheckOutcome(STATUS_OK, "API reachable, storage figures unavailable", elapsed)

    percent_free = (available_raw / size_raw) * 100
    message = f"{humanize_bytes(available_raw)} free ({percent_free:.1f}%)"
    if percent_free < fail_percent:
        return CheckOutcome(STATUS_FAIL, message, elapsed)
    if percent_free < warn_percent:
        return CheckOutcome(STATUS_WARN, message, elapsed)
    return CheckOutcome(STATUS_OK, message, elapsed)


async def check_immich_jobs(
    client: httpx.AsyncClient, base_url: str, api_key: str | None, config: dict
) -> CheckOutcome:
    """Background job queues (thumbnail generation, metadata extraction,
    facial recognition, etc.) - GET /api/jobs. Warns once any queue's failed
    count reaches the configured threshold; a queue that's merely busy or
    has a big backlog waiting isn't itself a problem, only jobs that
    actually failed are."""
    warn_failed = config.get("warn_failed_jobs", 1)

    url = base_url.rstrip("/") + API_PREFIX + "/jobs"
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
        return CheckOutcome(STATUS_FAIL, f"Jobs API returned HTTP {resp.status_code}", elapsed)

    try:
        data = resp.json()
    except ValueError:
        return CheckOutcome(STATUS_OK, "API reachable, job queue figures unavailable", elapsed)

    if not isinstance(data, dict):
        return CheckOutcome(STATUS_OK, "API reachable, job queue figures unavailable", elapsed)

    failed_total = 0
    failed_queues = []
    for queue_name, queue_info in data.items():
        if not isinstance(queue_info, dict):
            continue
        failed = (queue_info.get("jobCounts") or {}).get("failed")
        if isinstance(failed, (int, float)) and failed > 0:
            failed_total += failed
            failed_queues.append(f"{queue_name} ({int(failed)})")

    if failed_total == 0:
        return CheckOutcome(STATUS_OK, "No failed jobs", elapsed)
    message = f"{failed_total} failed job(s): {', '.join(failed_queues)}"
    if failed_total >= warn_failed:
        return CheckOutcome(STATUS_WARN, message, elapsed)
    return CheckOutcome(STATUS_OK, message, elapsed)
