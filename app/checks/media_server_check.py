import time

import httpx

from .base import STATUS_FAIL, STATUS_OK, STATUS_WARN, CheckOutcome

PLEX_TV_RESOURCES_URL = "https://plex.tv/api/v2/resources"


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


async def check_plex_remote_access(client: httpx.AsyncClient, api_key: str | None, config: dict) -> CheckOutcome:
    """Approximates the "Remote Access" indicator in Plex's own Settings page
    and, beyond just trusting plex.tv's bookkeeping, actually tries to reach
    the server at its public plex.direct address.

    Uses plex.tv's (undocumented but widely relied upon) v2 resources API,
    which lists every connection plex.tv knows about for this server,
    flagging each as local/relay/direct. No connection registered at all
    means Remote Access is off; only relay connections means it's degraded
    (Plex falls back to a slower relay when it can't establish a direct
    connection, e.g. port forwarding/UPnP failed); a reachable non-relay
    connection means Remote Access is genuinely working end-to-end.

    Needs outbound internet access from this container to plex.tv and to the
    server's own plex.direct address. Deliberately polled infrequently
    (see the built-in check's interval_seconds) since it depends on an
    external API and rarely changes minute to minute.
    """
    if not api_key:
        return CheckOutcome(STATUS_WARN, "No Plex token configured - cannot query plex.tv for Remote Access status", None)

    client_identifier = config.get("client_identifier")
    start = time.perf_counter()
    try:
        resp = await client.get(
            PLEX_TV_RESOURCES_URL,
            params={"includeHttps": 1, "includeRelay": 1, "X-Plex-Token": api_key},
            headers={"Accept": "application/json"},
        )
    except httpx.RequestError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"Could not reach plex.tv to check Remote Access: {exc}", elapsed)
    elapsed = (time.perf_counter() - start) * 1000

    if resp.status_code == 401:
        return CheckOutcome(STATUS_FAIL, "plex.tv rejected the configured token (HTTP 401)", elapsed)
    if resp.status_code != 200:
        return CheckOutcome(STATUS_FAIL, f"plex.tv resources API returned HTTP {resp.status_code}", elapsed)

    try:
        devices = resp.json()
    except ValueError:
        return CheckOutcome(STATUS_FAIL, "plex.tv resources API returned invalid JSON", elapsed)

    servers = [d for d in devices if "server" in (d.get("provides") or "").split(",")]
    if client_identifier:
        matched = [d for d in servers if d.get("clientIdentifier") == client_identifier]
        servers = matched or servers
    if not servers:
        return CheckOutcome(STATUS_WARN, "No Plex server found on this plex.tv account/token", elapsed)

    connections = servers[0].get("connections", [])
    direct = [c for c in connections if not c.get("local") and not c.get("relay") and c.get("uri")]
    relay = [c for c in connections if not c.get("local") and c.get("relay") and c.get("uri")]

    if not direct and not relay:
        return CheckOutcome(
            STATUS_FAIL, "Remote Access appears disabled - plex.tv has no public connection for this server", elapsed
        )

    for conn in direct:
        uri = conn["uri"]
        try:
            r2 = await client.get(f"{uri}/identity")
        except httpx.RequestError:
            continue
        if r2.status_code == 200:
            total_elapsed = (time.perf_counter() - start) * 1000
            return CheckOutcome(STATUS_OK, f"Remote Access OK - reachable directly at {uri}", total_elapsed)

    if direct:
        return CheckOutcome(
            STATUS_WARN,
            "Remote Access is registered with plex.tv but the plex.direct address didn't respond "
            "- check port forwarding/firewall",
            elapsed,
        )
    return CheckOutcome(
        STATUS_WARN,
        "Remote Access is only reachable via Plex Relay (direct connection failed) - streaming will be slower/limited",
        elapsed,
    )
