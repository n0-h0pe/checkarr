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
