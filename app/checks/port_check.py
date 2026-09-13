"""Raw TCP reachability probe against a host/port that has nothing to do
with the service's own configured local/remote address - built for
confirming a port-forwarded external address (e.g. Plex's forwarded port on
your router) actually has something listening on it.

Deliberately just a TCP connect-then-close, no protocol handshake beyond
that - "something answered" is all this claims, not "Plex answered"; that's
what plex_identity/plex_remote_access are for. See this check's own
CHECK_TYPE_META entry (routers/meta.py) and ConfiguringServices.md for the
NAT hairpin/loopback caveat that makes a FAIL here not always trustworthy
when Checkarr runs on the same network as the service it's testing.
"""

import asyncio
import time

from ..config import settings
from .base import STATUS_FAIL, STATUS_OK, CheckOutcome


async def check_external_port_open(config: dict) -> CheckOutcome:
    host = (config.get("host") or "").strip()
    port = config.get("port")
    if not host:
        return CheckOutcome(STATUS_FAIL, "No static IP/hostname configured", None)
    if not port:
        return CheckOutcome(STATUS_FAIL, "No external port configured", None)
    port = int(port)

    start = time.perf_counter()
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=settings.http_timeout_seconds
        )
    except asyncio.TimeoutError:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(
            STATUS_FAIL, f"{host}:{port} did not respond within {settings.http_timeout_seconds:.0f}s", elapsed
        )
    except OSError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"{host}:{port} unreachable - {exc}", elapsed)
    elapsed = (time.perf_counter() - start) * 1000

    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass  # connection already gone - nothing left to clean up

    return CheckOutcome(STATUS_OK, f"{host}:{port} is open and accepting connections", elapsed)
