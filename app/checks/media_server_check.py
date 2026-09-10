import time

import httpx

from .base import STATUS_FAIL, STATUS_OK, CheckOutcome


async def check_plex_identity(client: httpx.AsyncClient, base_url: str, api_key: str | None, config: dict) -> CheckOutcome:
    """Plex's /identity endpoint is unauthenticated and cheap - good liveness probe."""
    url = base_url.rstrip("/") + "/identity"
    headers = {"X-Plex-Token": api_key} if api_key else {}
    start = time.perf_counter()
    try:
        resp = await client.get(url, headers=headers)
    except httpx.RequestError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"Request to {url} failed: {exc}", elapsed)
    elapsed = (time.perf_counter() - start) * 1000

    if resp.status_code != 200:
        return CheckOutcome(STATUS_FAIL, f"{url} returned HTTP {resp.status_code}", elapsed)
    return CheckOutcome(STATUS_OK, "Plex Media Server identity responded OK", elapsed)


async def check_jellyfin_health(client: httpx.AsyncClient, base_url: str, api_key: str | None, config: dict) -> CheckOutcome:
    """Jellyfin exposes a plain /health endpoint returning the text 'Healthy'."""
    url = base_url.rstrip("/") + "/health"
    start = time.perf_counter()
    try:
        resp = await client.get(url)
    except httpx.RequestError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"Request to {url} failed: {exc}", elapsed)
    elapsed = (time.perf_counter() - start) * 1000

    if resp.status_code != 200:
        return CheckOutcome(STATUS_FAIL, f"{url} returned HTTP {resp.status_code}", elapsed)
    body = resp.text.strip()
    if body and "healthy" not in body.lower():
        return CheckOutcome(STATUS_FAIL, f"Jellyfin health endpoint reported: {body}", elapsed)
    return CheckOutcome(STATUS_OK, "Jellyfin reported Healthy", elapsed)
