"""Backs the "Test connection" button in the Add/Edit service form - a
quick, type-aware reachability probe run before a service is even saved.
"""

import httpx

from . import schemas
from .config import settings

_TIMEOUT = min(settings.http_timeout_seconds, 8.0)


async def _probe(client: httpx.AsyncClient, service_type: str, url: str, api_key: str | None) -> schemas.ConnectionTestResult:
    url = url.rstrip("/")
    if service_type == "plex":
        target = f"{url}/identity"
        headers = {"X-Plex-Token": api_key} if api_key else {}
    elif service_type == "jellyfin":
        target = f"{url}/health"
        headers = {}
    else:
        target = url
        headers = {}

    try:
        resp = await client.get(target, headers=headers, follow_redirects=True)
    except httpx.RequestError as exc:
        return schemas.ConnectionTestResult(ok=False, message=f"Could not connect: {exc}")

    if resp.status_code < 400:
        return schemas.ConnectionTestResult(ok=True, message=f"HTTP {resp.status_code}")
    if resp.status_code == 401:
        return schemas.ConnectionTestResult(ok=False, message="HTTP 401 - reachable, but needs auth (check API key)")
    return schemas.ConnectionTestResult(ok=False, message=f"HTTP {resp.status_code}")


async def test_connection(payload: schemas.ConnectionTestRequest) -> schemas.ConnectionTestResponse:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        local = (
            await _probe(client, payload.type, payload.local_url, payload.api_key)
            if payload.local_url
            else None
        )
        remote = (
            await _probe(client, payload.type, payload.remote_url, payload.api_key)
            if payload.remote_url
            else None
        )
    return schemas.ConnectionTestResponse(local=local, remote=remote)
