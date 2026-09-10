"""Shared constants/helpers for talking to plex.tv and Plex Media Server's
own undocumented-but-stable API. Plex's v2 plex.tv endpoints reject requests
missing these identifying headers with a plain HTTP 400 - easy to trip over
(and the original plex_remote_access check did).
"""

from .version import VERSION

# Fixed, non-secret identifier for this app as a Plex "client" - stable
# across installs so a signed-in PIN authorization always maps back to us.
PLEX_CLIENT_IDENTIFIER = "healthchecker-4b3f2a6e-9c1d-4a7b-9e2f-2f6a8c1d5e7b"
PLEX_PRODUCT = "Media Estate HealthChecker"


def plex_tv_headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "X-Plex-Client-Identifier": PLEX_CLIENT_IDENTIFIER,
        "X-Plex-Product": PLEX_PRODUCT,
        "X-Plex-Version": VERSION,
    }
    if token:
        headers["X-Plex-Token"] = token
    return headers
