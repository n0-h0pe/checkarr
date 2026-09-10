"""Shared helper for Jellyfin's admin-only endpoints (library listing,
filesystem browsing). Jellyfin's static API keys (Dashboard > API Keys) are
meant to carry whatever role the admin who created them has, but in
practice some admin-gated endpoints reject them anyway - a known
inconsistency in Jellyfin's API, not something this app can work around on
the key side. Logging in as a real user via /Users/AuthenticateByName
produces a token tied to that user's actual role instead, which those
endpoints accept reliably.
"""

import httpx

from .version import VERSION

# Jellyfin's auth middleware needs this to identify the calling client on
# every request, including the login call itself - both header names are
# sent since Jellyfin has supported the two interchangeably across versions
# (X-Emby-Authorization is the long-standing name; Authorization is what a
# reverse proxy is guaranteed to forward untouched, since it's a standard
# header where X-Emby-Authorization is not always allow-listed by a
# proxy config someone copied from an older guide).
_CLIENT_AUTH_VALUE = f'MediaBrowser Client="Checkarr", Device="Checkarr", DeviceId="checkarr-healthcheck", Version="{VERSION}"'
JELLYFIN_AUTH_HEADERS = {
    "X-Emby-Authorization": _CLIENT_AUTH_VALUE,
    "Authorization": _CLIENT_AUTH_VALUE,
}


class JellyfinAdminAuthError(Exception):
    pass


async def get_jellyfin_admin_token(client: httpx.AsyncClient, base_url: str, username: str, password: str) -> str:
    url = base_url.rstrip("/") + "/Users/AuthenticateByName"
    headers = {"Content-Type": "application/json", "Accept": "application/json", **JELLYFIN_AUTH_HEADERS}
    try:
        resp = await client.post(url, json={"Username": username, "Pw": password}, headers=headers)
    except httpx.RequestError as exc:
        raise JellyfinAdminAuthError(f"Could not reach {url}: {exc}") from exc

    if resp.status_code == 401:
        raise JellyfinAdminAuthError("Admin login rejected (HTTP 401) - check the admin username/password")
    if resp.status_code != 200:
        # Jellyfin's own error body (when present) is usually far more
        # specific than the status code alone - e.g. a 400 here is often a
        # validation message pointing at exactly what it didn't like.
        detail = resp.text.strip()[:300]
        suffix = f" - server said: {detail}" if detail else ""
        raise JellyfinAdminAuthError(f"Admin login returned HTTP {resp.status_code}{suffix}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise JellyfinAdminAuthError("Admin login response was not valid JSON") from exc

    token = data.get("AccessToken")
    if not token:
        raise JellyfinAdminAuthError("Admin login succeeded but no AccessToken was returned")
    return token
