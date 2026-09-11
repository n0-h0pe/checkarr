import time
import xmlrpc.client as xmlrpc_client

import httpx

from .base import STATUS_FAIL, STATUS_OK, STATUS_WARN, CheckOutcome, humanize_bytes

GIB = 1024 ** 3


async def _qbittorrent_login(
    client: httpx.AsyncClient, base_url: str, username: str | None, password: str | None
) -> tuple[bool, str, float]:
    """Shared by check_qbittorrent_login and check_qbittorrent_disk_space -
    both need a real session (qBittorrent uses a session cookie, not a
    bearer key) before anything past the login endpoint will respond.
    Returns (ok, message-if-failed, elapsed_ms)."""
    url = base_url.rstrip("/") + "/api/v2/auth/login"
    start = time.perf_counter()
    try:
        resp = await client.post(url, data={"username": username or "", "password": password or ""})
    except httpx.RequestError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return False, f"Request to {url} failed: {exc}", elapsed
    elapsed = (time.perf_counter() - start) * 1000

    if resp.status_code == 403:
        return False, "Login rejected (HTTP 403) - too many failed attempts may have locked qBittorrent's WebUI", elapsed
    if resp.status_code not in (200, 204):
        return False, f"Login endpoint returned HTTP {resp.status_code}", elapsed

    body = resp.text.strip()
    if body and body.lower() != "ok.":
        return False, f"Login failed - check the configured username/password (server said: {body})", elapsed
    return True, "", elapsed


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

    ok, err, elapsed = await _qbittorrent_login(client, base_url, username, password)
    if not ok:
        return CheckOutcome(STATUS_FAIL, err, elapsed)
    return CheckOutcome(STATUS_OK, "Logged in to qBittorrent WebUI API successfully", elapsed)


async def check_qbittorrent_disk_space(
    client: httpx.AsyncClient, base_url: str, username: str | None, password: str | None, config: dict
) -> CheckOutcome:
    """Free space on qBittorrent's default save path, via its WebUI API
    (GET /api/v2/sync/maindata -> server_state.free_space_on_disk).

    qBittorrent's API reports free bytes but not the disk's total capacity,
    so there's nothing to compute a percentage against unless that total is
    supplied below - see the "Total disk size" field's hint for why, and
    _disk_space_outcome() for what happens with/without it.
    """
    if username or password:
        ok, err, elapsed_login = await _qbittorrent_login(client, base_url, username, password)
        if not ok:
            return CheckOutcome(STATUS_FAIL, err, elapsed_login)

    url = base_url.rstrip("/") + "/api/v2/sync/maindata"
    start = time.perf_counter()
    try:
        resp = await client.get(url)
    except httpx.RequestError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"Request to {url} failed: {exc}", elapsed)
    elapsed = (time.perf_counter() - start) * 1000

    if resp.status_code == 403:
        return CheckOutcome(STATUS_FAIL, "Not authenticated (HTTP 403) - check the configured username/password", elapsed)
    if resp.status_code != 200:
        return CheckOutcome(STATUS_FAIL, f"{url} returned HTTP {resp.status_code}", elapsed)

    try:
        free_bytes = resp.json()["server_state"]["free_space_on_disk"]
    except (ValueError, KeyError, TypeError) as exc:
        return CheckOutcome(STATUS_FAIL, f"Could not read free space from qBittorrent's response: {exc}", elapsed)

    return _disk_space_outcome(free_bytes, config, elapsed, "default save path")


async def _deluge_login(client: httpx.AsyncClient, base_url: str, password: str) -> tuple[bool, str, float]:
    """Shared by check_deluge_login and check_deluge_disk_space - Deluge's
    JSON-RPC session also needs an explicit auth.login call first. Returns
    (ok, message-if-failed, elapsed_ms)."""
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
        return False, f"Request to {url} failed: {exc}", elapsed
    elapsed = (time.perf_counter() - start) * 1000

    if resp.status_code != 200:
        return False, f"Login endpoint returned HTTP {resp.status_code}", elapsed
    try:
        data = resp.json()
    except ValueError:
        return False, "Login endpoint returned invalid JSON - is this actually Deluge's WebUI?", elapsed

    if data.get("error"):
        return False, f"Login error: {data['error'].get('message', data['error'])}", elapsed
    if data.get("result") is not True:
        return False, "Login failed - check the configured password", elapsed
    return True, "", elapsed


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

    ok, err, elapsed = await _deluge_login(client, base_url, password)
    if not ok:
        return CheckOutcome(STATUS_FAIL, err, elapsed)
    return CheckOutcome(STATUS_OK, "Logged in to Deluge WebUI API successfully", elapsed)


async def check_deluge_disk_space(
    client: httpx.AsyncClient, base_url: str, password: str | None, config: dict
) -> CheckOutcome:
    """Free space at a path via Deluge's JSON-RPC API (core.get_free_space) -
    defaults to Deluge's own download location when no path is given. Like
    qBittorrent, Deluge's API reports free bytes only, not total capacity;
    see _disk_space_outcome() for how the percentage thresholds handle that.
    """
    path = (config.get("path") or "").strip() or None

    if password:
        ok, err, elapsed_login = await _deluge_login(client, base_url, password)
        if not ok:
            return CheckOutcome(STATUS_FAIL, err, elapsed_login)

    url = base_url.rstrip("/") + "/json"
    start = time.perf_counter()
    try:
        resp = await client.post(
            url,
            json={"id": 1, "method": "core.get_free_space", "params": [path]},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
    except httpx.RequestError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"Request to {url} failed: {exc}", elapsed)
    elapsed = (time.perf_counter() - start) * 1000

    if resp.status_code != 200:
        return CheckOutcome(STATUS_FAIL, f"{url} returned HTTP {resp.status_code}", elapsed)
    try:
        data = resp.json()
    except ValueError:
        return CheckOutcome(STATUS_FAIL, "Endpoint returned invalid JSON - is this actually Deluge's WebUI?", elapsed)

    if data.get("error"):
        return CheckOutcome(STATUS_FAIL, f"core.get_free_space error: {data['error'].get('message', data['error'])}", elapsed)
    free_bytes = data.get("result")
    if not isinstance(free_bytes, (int, float)):
        return CheckOutcome(STATUS_FAIL, "Could not read free space from Deluge's response", elapsed)

    return _disk_space_outcome(free_bytes, config, elapsed, path or "download location")


def _disk_space_outcome(free_bytes: float, config: dict, elapsed: float, label: str) -> CheckOutcome:
    """Both torrent clients' APIs report free bytes only, not the disk's
    total capacity, so a percentage-of-total threshold needs that total
    supplied manually in the check's config (it rarely changes, unlike free
    space). Without it, this just reports the free space with no threshold
    applied - still useful at a glance, just not something that can page you.
    ("(%?)" is deliberately terse - the Edit check panel's own hint explains
    it in full; this message has to share a dashboard card row with the
    check's name.)
    """
    free_str = humanize_bytes(free_bytes)
    total_gb = config.get("total_disk_gb")
    if not total_gb:
        return CheckOutcome(STATUS_OK, f"{label}: {free_str} free (%?)", elapsed)

    warn_percent = config.get("warn_percent", 10)
    fail_percent = config.get("fail_percent", 3)
    total_bytes = total_gb * GIB
    percent_free = (free_bytes / total_bytes) * 100

    if percent_free < fail_percent:
        status = STATUS_FAIL
    elif percent_free < warn_percent:
        status = STATUS_WARN
    else:
        status = STATUS_OK
    return CheckOutcome(
        status, f"{label}: {free_str} free ({percent_free:.1f}% of {humanize_bytes(total_bytes)})", elapsed
    )


async def check_rtorrent_rpc_status(
    client: httpx.AsyncClient, base_url: str, config: dict, auth: tuple[str, str] | None = None
) -> CheckOutcome:
    """Shared by both the "rtorrent" (bare) and "rutorrent" (ruTorrent
    web frontend) service types - rTorrent itself has no web UI or REST API
    of its own either way, so this speaks its XML-RPC interface directly
    (the same protocol ruTorrent uses under the hood), POSTing a
    `system.client_version` call to the configured path and treating any
    valid, non-fault XML-RPC response as reachable.

    The path varies by setup, which is why the two service types default
    their auto-created check to a different one (see
    checks.runner.default_checks_for_service_type): plain `/RPC2` for
    "rtorrent" - a bare XML-RPC-over-HTTP bridge (e.g. via
    xmlrpc.scgi_port + a webserver proxy) with no ruTorrent in front of it
    at all - or `/rutorrent/plugins/httprpc/action.php` for "rutorrent",
    its httprpc plugin's usual path. Older ruTorrent setups instead use
    `/plugins/rpc/rpc.php`. There's no way to auto-detect which of these a
    given install actually uses, so it isn't guessed beyond that per-type
    default - if this check fails with a 404, that's almost always the fix.

    rTorrent's XML-RPC interface has no disk-space method (unlike qBittorrent/
    Deluge's own APIs), so there's no equivalent free-space check for it.
    """
    rpc_path = (config.get("rpc_path") or "/RPC2").strip()
    url = base_url.rstrip("/") + "/" + rpc_path.lstrip("/")
    body = xmlrpc_client.dumps((), methodname="system.client_version").encode("utf-8")

    start = time.perf_counter()
    try:
        resp = await client.post(url, content=body, headers={"Content-Type": "text/xml"}, auth=auth)
    except httpx.RequestError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"Request to {url} failed: {exc}", elapsed)
    elapsed = (time.perf_counter() - start) * 1000

    if resp.status_code == 404:
        return CheckOutcome(STATUS_FAIL, f"{url} returned HTTP 404 - check the URL Path (see this check's hint)", elapsed)
    if resp.status_code != 200:
        return CheckOutcome(STATUS_FAIL, f"{url} returned HTTP {resp.status_code}", elapsed)

    try:
        result, _method = xmlrpc_client.loads(resp.text)
    except xmlrpc_client.Fault as exc:
        return CheckOutcome(STATUS_FAIL, f"XML-RPC fault from rTorrent: {exc.faultString}", elapsed)
    except Exception as exc:  # noqa: BLE001 - anything else means this wasn't a valid XML-RPC response
        return CheckOutcome(STATUS_FAIL, f"{url} did not return a valid XML-RPC response - check the URL Path: {exc}", elapsed)

    version = result[0] if result else "unknown"
    return CheckOutcome(STATUS_OK, f"rTorrent XML-RPC reachable at {rpc_path} (client version {version})", elapsed)
