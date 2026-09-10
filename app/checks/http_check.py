import time

import httpx

from .base import STATUS_FAIL, STATUS_OK, STATUS_WARN, CheckOutcome


async def check_http_200(client: httpx.AsyncClient, base_url: str, config: dict) -> CheckOutcome:
    """Generic "is the web UI up" check: GET a URL, expect an allowed status code."""
    path = (config.get("path") or "").strip()
    url = _join(base_url, path)
    expected = config.get("expected_status_codes") or [200]
    method = (config.get("method") or "GET").upper()

    start = time.perf_counter()
    try:
        resp = await client.request(method, url, follow_redirects=True)
    except httpx.RequestError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"Request to {url} failed: {exc}", elapsed)
    elapsed = (time.perf_counter() - start) * 1000

    if resp.status_code not in expected:
        return CheckOutcome(
            STATUS_FAIL,
            f"{url} returned HTTP {resp.status_code}, expected one of {expected}",
            elapsed,
        )
    return CheckOutcome(STATUS_OK, f"{url} responded HTTP {resp.status_code}", elapsed)


async def check_keyword_match(client: httpx.AsyncClient, base_url: str, config: dict) -> CheckOutcome:
    """GET a URL and require (or forbid) a substring in the response body."""
    path = (config.get("path") or "").strip()
    url = _join(base_url, path)
    keyword = config.get("keyword", "")
    mode = config.get("mode", "must_contain")  # must_contain | must_not_contain

    start = time.perf_counter()
    try:
        resp = await client.get(url, follow_redirects=True)
    except httpx.RequestError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"Request to {url} failed: {exc}", elapsed)
    elapsed = (time.perf_counter() - start) * 1000

    if resp.status_code >= 400:
        return CheckOutcome(STATUS_FAIL, f"{url} returned HTTP {resp.status_code}", elapsed)

    body = resp.text
    found = keyword in body
    if mode == "must_contain" and not found:
        return CheckOutcome(STATUS_WARN, f"Expected keyword '{keyword}' not found at {url}", elapsed)
    if mode == "must_not_contain" and found:
        return CheckOutcome(STATUS_WARN, f"Forbidden keyword '{keyword}' found at {url}", elapsed)
    return CheckOutcome(STATUS_OK, f"{url} matched keyword rule", elapsed)


def _join(base_url: str, path: str) -> str:
    if not path:
        return base_url
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return base_url.rstrip("/") + "/" + path.lstrip("/")
