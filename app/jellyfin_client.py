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
_CLIENT_AUTH_FIELDS = f'Client="Checkarr", Device="Checkarr", DeviceId="checkarr-healthcheck", Version="{VERSION}"'
JELLYFIN_AUTH_HEADERS = {
    "X-Emby-Authorization": f"MediaBrowser {_CLIENT_AUTH_FIELDS}",
    "Authorization": f"MediaBrowser {_CLIENT_AUTH_FIELDS}",
}


def jellyfin_auth_headers(token: str | None = None) -> dict[str, str]:
    """Same client-identification headers as JELLYFIN_AUTH_HEADERS, plus the
    given access token/API key. The token is embedded directly in the
    MediaBrowser auth string (Jellyfin's documented, preferred way to carry
    it) *and* sent as the legacy X-Emby-Token header - some admin-gated
    endpoints (e.g. /Library/VirtualFolders) have been observed rejecting a
    token presented only via X-Emby-Token with a 401 even though it's valid,
    while accepting the same token embedded in Authorization."""
    if not token:
        return dict(JELLYFIN_AUTH_HEADERS)
    value = f'MediaBrowser {_CLIENT_AUTH_FIELDS}, Token="{token}"'
    return {"X-Emby-Authorization": value, "Authorization": value, "X-Emby-Token": token}


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
