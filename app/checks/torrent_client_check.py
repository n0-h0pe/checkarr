import time

import httpx

from .base import STATUS_FAIL, STATUS_OK, STATUS_WARN, CheckOutcome


async def check_qbittorrent_login(
    client: httpx.AsyncClient, base_url: str, username: str | None, password: str | None, config: dict
) -> CheckOutcome:
    """Confirms qBittorrent's WebUI API actually accepts the configured
    credentials, via its real login endpoint (POST /api/v2/auth/login) -
    qBittorrent uses a session-cookie login, not a bearer API key.

    No-ops (OK) if no username/password is configured, since qBittorrent's
    WebUI can have authentication disabled entirely - in that case the
    "Web UI reachable" check is all there is to verify.
    """
    if not username and not password:
        return CheckOutcome(STATUS_OK, "No credentials configured - skipping login check (WebUI auth may be disabled)", None)

    url = base_url.rstrip("/") + "/api/v2/auth/login"
    start = time.perf_counter()
    try:
        resp = await client.post(url, data={"username": username or "", "password": password or ""})
    except httpx.RequestError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"Request to {url} failed: {exc}", elapsed)
    elapsed = (time.perf_counter() - start) * 1000

    if resp.status_code == 403:
        return CheckOutcome(STATUS_FAIL, "Login rejected (HTTP 403) - too many failed attempts may have locked qBittorrent's WebUI", elapsed)
    if resp.status_code not in (200, 204):
        return CheckOutcome(STATUS_FAIL, f"Login endpoint returned HTTP {resp.status_code}", elapsed)

    body = resp.text.strip()
    if body and body.lower() != "ok.":
        return CheckOutcome(STATUS_FAIL, f"Login failed - check the configured username/password (server said: {body})", elapsed)
    return CheckOutcome(STATUS_OK, "Logged in to qBittorrent WebUI API successfully", elapsed)


async def check_deluge_login(
    client: httpx.AsyncClient, base_url: str, password: str | None, config: dict
) -> CheckOutcome:
    """Confirms Deluge's WebUI JSON-RPC API accepts the configured password
    (POST /json, method auth.login - Deluge's web UI has no username, just a
    single shared password).

    No-ops (OK) if no password is configured, since Deluge's WebUI can be
    set to skip the login page entirely for local/trusted networks.
    """
    if not password:
        return CheckOutcome(STATUS_OK, "No password configured - skipping login check (WebUI auth may be disabled)", None)

    url = base_url.rstrip("/") + "/json"
    start = time.perf_counter()
    try:
        resp = await client.post(
            url,
            json={"id": 1, "method": "auth.login", "params": [password]},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
    except httpx.RequestError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"Request to {url} failed: {exc}", elapsed)
    elapsed = (time.perf_counter() - start) * 1000

    if resp.status_code != 200:
        return CheckOutcome(STATUS_FAIL, f"Login endpoint returned HTTP {resp.status_code}", elapsed)

    try:
        data = resp.json()
    except ValueError:
        return CheckOutcome(STATUS_FAIL, "Login endpoint returned invalid JSON - is this actually Deluge's WebUI?", elapsed)

    if data.get("error"):
        return CheckOutcome(STATUS_FAIL, f"Login error: {data['error'].get('message', data['error'])}", elapsed)
    if data.get("result") is not True:
        return CheckOutcome(STATUS_FAIL, "Login failed - check the configured password", elapsed)
    return CheckOutcome(STATUS_OK, "Logged in to Deluge WebUI API successfully", elapsed)
