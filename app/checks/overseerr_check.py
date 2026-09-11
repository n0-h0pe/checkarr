import time

import httpx

from .base import STATUS_FAIL, STATUS_OK, CheckOutcome, build_headers

API_PREFIX = "/api/v1"


async def check_overseerr_status(client: httpx.AsyncClient, base_url: str, api_key: str | None, config: dict) -> CheckOutcome:
    """Confirms the app itself (not just its reverse proxy/web UI) is up and
    the API key works - GET /api/v1/status, the same endpoint Seerr's
    own update-checker widget polls. Works identically for Jellyseerr,
    which is an API-compatible fork.
    """
    url = base_url.rstrip("/") + API_PREFIX + "/status"
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
        return CheckOutcome(STATUS_FAIL, f"Status API returned HTTP {resp.status_code}", elapsed)

    try:
        version = resp.json().get("version", "unknown")
    except ValueError:
        version = "unknown"
    return CheckOutcome(STATUS_OK, f"API reachable, version {version}", elapsed)


async def check_overseerr_tmdb_status(
    client: httpx.AsyncClient, base_url: str, api_key: str | None, config: dict
) -> CheckOutcome:
    """Seerr/Jellyseerr pull all movie/TV metadata from TMDB (The Movie
    Database) - there's no dedicated "test TMDB" endpoint, so this hits
    /api/v1/discover/trending instead, the same call Seerr's own
    homepage "Trending" carousel makes on every page load. A working
    response means the whole path - Seerr to TMDB and back - is intact;
    a failure here is a TMDB-side or connectivity problem, not necessarily
    Seerr itself (which is why "Status" above is a separate check).
    """
    url = base_url.rstrip("/") + API_PREFIX + "/discover/trending"
    start = time.perf_counter()
    try:
        resp = await client.get(url, headers=build_headers(api_key))
    except httpx.RequestError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"Request to {url} failed: {exc}", elapsed)
    elapsed = (time.perf_counter() - start) * 1000

    if resp.status_code == 401:
        return CheckOutcome(STATUS_FAIL, "API key rejected (HTTP 401) - check the configured key", elapsed)
    if resp.status_code != 200:
        return CheckOutcome(STATUS_FAIL, f"TMDB-backed discover API returned HTTP {resp.status_code}", elapsed)

    try:
        data = resp.json()
    except ValueError:
        return CheckOutcome(STATUS_FAIL, "TMDB-backed discover API returned invalid JSON", elapsed)

    results = data.get("results")
    if not isinstance(results, list):
        return CheckOutcome(STATUS_FAIL, "TMDB-backed discover API response had no results list", elapsed)
    return CheckOutcome(STATUS_OK, f"TMDB reachable via Seerr - {len(results)} trending result(s)", elapsed)
