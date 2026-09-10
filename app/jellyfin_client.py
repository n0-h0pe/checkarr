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

# Jellyfin rejects requests with no client-identifying header at all on some
# endpoints, so this is always sent, not just for the login call itself.
JELLYFIN_CLIENT_HEADER = f'MediaBrowser Client="Checkarr", Device="Checkarr", DeviceId="checkarr-healthcheck", Version="{VERSION}"'


class JellyfinAdminAuthError(Exception):
    pass


async def get_jellyfin_admin_token(client: httpx.AsyncClient, base_url: str, username: str, password: str) -> str:
    url = base_url.rstrip("/") + "/Users/AuthenticateByName"
    headers = {"Content-Type": "application/json", "X-Emby-Authorization": JELLYFIN_CLIENT_HEADER}
    try:
        resp = await client.post(url, json={"Username": username, "Pw": password}, headers=headers)
    except httpx.RequestError as exc:
        raise JellyfinAdminAuthError(f"Could not reach {url}: {exc}") from exc

    if resp.status_code == 401:
        raise JellyfinAdminAuthError("Admin login rejected (HTTP 401) - check the admin username/password")
    if resp.status_code != 200:
        raise JellyfinAdminAuthError(f"Admin login returned HTTP {resp.status_code}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise JellyfinAdminAuthError("Admin login response was not valid JSON") from exc

    token = data.get("AccessToken")
    if not token:
        raise JellyfinAdminAuthError("Admin login succeeded but no AccessToken was returned")
    return token
