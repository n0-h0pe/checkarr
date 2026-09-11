import asyncio
import socket
import ssl
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from .base import STATUS_FAIL, STATUS_OK, STATUS_WARN, CheckOutcome

_CERT_DATE_FORMAT = "%b %d %H:%M:%S %Y %Z"
_DEFAULT_EXPIRY_WARN_DAYS = 14


def _check_sync(host: str, port: int) -> tuple[str, str]:
    """Blocking - socket/ssl have no async API, so this runs off the event
    loop via asyncio.to_thread below. Uses a strict default context
    regardless of the service's own connection settings (see poller.py -
    ordinary checks no longer verify certs at all; this check is the one
    place that still does, on purpose)."""
    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=10) as sock:
        with context.wrap_socket(sock, server_hostname=host) as ssock:
            cert = ssock.getpeercert()
    not_after = cert.get("notAfter") if cert else None
    if not not_after:
        raise ValueError("certificate has no expiry information")
    return not_after, ""


async def check_ssl_certificate(base_url: str | None, config: dict) -> CheckOutcome:
    """Validates the actual TLS certificate for an https:// address -
    trusted chain, hostname match, not expired/expiring soon. Auto-generated
    for every https:// address a service has (see _maybe_add_ssl_check in
    routers/services.py); poller.py only ever schedules this against https
    targets, so the "not applicable" branch below is just a defensive
    fallback, not something normally hit."""
    if not base_url or not base_url.lower().startswith("https://"):
        return CheckOutcome(STATUS_OK, "Not applicable - address is not HTTPS")

    parsed = urlparse(base_url)
    host = parsed.hostname
    port = parsed.port or 443
    if not host:
        return CheckOutcome(STATUS_FAIL, f"Could not parse a host from {base_url}")

    expiry_warn_days = config.get("expiry_warn_days")
    if not isinstance(expiry_warn_days, (int, float)) or expiry_warn_days <= 0:
        expiry_warn_days = _DEFAULT_EXPIRY_WARN_DAYS

    start = time.perf_counter()
    try:
        not_after, _ = await asyncio.to_thread(_check_sync, host, port)
    except ssl.SSLCertVerificationError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"Certificate not trusted for {host}: {exc.verify_message or exc}", elapsed)
    except (ssl.SSLError, OSError, ValueError) as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"Could not verify certificate for {host}: {exc}", elapsed)
    elapsed = (time.perf_counter() - start) * 1000

    expires = datetime.strptime(not_after, _CERT_DATE_FORMAT).replace(tzinfo=timezone.utc)
    days_left = (expires - datetime.now(timezone.utc)).total_seconds() / 86400
    expiry_label = expires.strftime("%Y-%m-%d")

    if days_left < 0:
        return CheckOutcome(STATUS_FAIL, f"Certificate for {host} expired {expiry_label}", elapsed)
    if days_left < expiry_warn_days:
        return CheckOutcome(
            STATUS_WARN, f"Certificate for {host} expires soon ({expiry_label}, {int(days_left)}d left)", elapsed
        )
    return CheckOutcome(STATUS_OK, f"Certificate for {host} valid until {expiry_label} ({int(days_left)}d left)", elapsed)
