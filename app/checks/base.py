from dataclasses import dataclass, field
from typing import Any

STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_FAIL = "fail"

# Worst-first ordering, used to roll many check results up into one service status.
STATUS_SEVERITY = {STATUS_OK: 0, STATUS_WARN: 1, STATUS_FAIL: 2}


@dataclass
class NotificationItem:
    source: str
    severity: str
    message: str
    wiki_url: str | None = None


@dataclass
class CheckOutcome:
    status: str
    message: str
    response_time_ms: float | None = None
    notifications: list[NotificationItem] = field(default_factory=list)


class CheckError(Exception):
    """Raised by a check implementation for a handled/expected failure."""


def worst_status(statuses: list[str]) -> str:
    if not statuses:
        return "unknown"
    return max(statuses, key=lambda s: STATUS_SEVERITY.get(s, 0))


def build_headers(api_key: str | None, extra: dict[str, Any] | None = None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if api_key:
        headers["X-Api-Key"] = api_key
    if extra:
        headers.update(extra)
    return headers


def humanize_bytes(num_bytes: float) -> str:
    """Auto-scaled size for disk-space check messages - TB above 1024 GB, GB
    above 1024 MB, and so on down to bytes, each with just enough decimal
    precision to be useful at that magnitude (a reading in the tens of GB
    doesn't need 2 decimal places; one just over 1 TB does). No space before
    the unit - keeps these status messages as short as possible, since they
    compete with the check name for room on a dashboard card."""
    step = 1024.0
    if num_bytes >= step**4:
        return f"{num_bytes / step**4:.2f}TB"
    if num_bytes >= step**3:
        return f"{num_bytes / step**3:.1f}GB"
    if num_bytes >= step**2:
        return f"{num_bytes / step**2:.0f}MB"
    if num_bytes >= step:
        return f"{num_bytes / step:.0f}KB"
    return f"{num_bytes:.0f}B"
