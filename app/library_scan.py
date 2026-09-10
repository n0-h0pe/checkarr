"""Backs "Scan libraries" - queries Plex/Jellyfin for their configured
library folders and turns each into its own arr_filesystem_path-style check,
via the same browse APIs those checks already use (no bind-mount needed).
"""

import xml.etree.ElementTree as ET

import httpx


class LibraryScanError(Exception):
    pass


async def scan_plex_libraries(client: httpx.AsyncClient, base_url: str, api_key: str | None) -> list[tuple[str, str]]:
    """Returns (library_title, path) pairs from GET /library/sections."""
    if not api_key:
        raise LibraryScanError("No X-Plex-Token configured")

    url = base_url.rstrip("/") + "/library/sections"
    try:
        resp = await client.get(url, headers={"X-Plex-Token": api_key})
    except httpx.RequestError as exc:
        raise LibraryScanError(f"Could not reach {url}: {exc}") from exc

    if resp.status_code == 401:
        raise LibraryScanError("API key rejected (HTTP 401)")
    if resp.status_code != 200:
        raise LibraryScanError(f"{url} returned HTTP {resp.status_code}")

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        raise LibraryScanError("Library sections response was not valid XML") from exc

    results: list[tuple[str, str]] = []
    for directory in root.findall("Directory"):
        title = directory.attrib.get("title", "Library")
        for location in directory.findall("Location"):
            path = location.attrib.get("path")
            if path:
                results.append((title, path))
    return results


async def scan_jellyfin_libraries(client: httpx.AsyncClient, base_url: str, api_key: str | None) -> list[tuple[str, str]]:
    """Returns (library_name, path) pairs from GET /Library/VirtualFolders."""
    if not api_key:
        raise LibraryScanError("No API key configured")

    url = base_url.rstrip("/") + "/Library/VirtualFolders"
    try:
        resp = await client.get(url, headers={"X-Emby-Token": api_key})
    except httpx.RequestError as exc:
        raise LibraryScanError(f"Could not reach {url}: {exc}") from exc

    if resp.status_code == 401:
        raise LibraryScanError("API key rejected (HTTP 401)")
    if resp.status_code == 403:
        raise LibraryScanError("API key rejected (HTTP 403) - this endpoint needs an administrator account/key")
    if resp.status_code != 200:
        raise LibraryScanError(f"{url} returned HTTP {resp.status_code}")

    try:
        folders = resp.json()
    except ValueError as exc:
        raise LibraryScanError("Virtual folders response was not valid JSON") from exc

    results: list[tuple[str, str]] = []
    for folder in folders:
        name = folder.get("Name", "Library")
        for path in folder.get("Locations") or []:
            results.append((name, path))
    return results
