"""Dispatches outbound alerts (Settings > Push Notifications) to every
enabled channel opted into the given severity tier. Adding a new channel
type later means one new function in app/notifiers/ and one entry in
_SENDERS below - see NOTIFICATION_CHANNEL_TYPE_META in routers/meta.py for
the matching frontend-config side of that.

Nothing calls dispatch_alert directly anymore except queue_alert's own
flush - everyone else (poller.py, housekeeping.py) goes through
queue_alert, which coalesces every alert raised within a rolling 10-second
window into one combined send instead of one send per alert. That's what
keeps a service that trips several checks at once, or flaps repeatedly,
from blowing through a notification provider's own rate limit - at most one
flush every 10 seconds, so at most 6 sends/minute regardless of how many
individual alerts fire.
"""

import asyncio
import logging
import threading

from . import models
from .database import SessionLocal
from .notifiers.browser import send_browser_notification
from .notifiers.discord import send_discord
from .notifiers.email import send_email
from .notifiers.pushbullet import send_pushbullet
from .notifiers.pushover import send_pushover
from .notifiers.slack import send_slack
from .notifiers.telegram import send_telegram
from .notifiers.webhook import send_webhook

_SENDERS = {
    "email": send_email,
    "discord": send_discord,
    "slack": send_slack,
    "telegram": send_telegram,
    "pushbullet": send_pushbullet,
    "pushover": send_pushover,
    "webhook": send_webhook,
    "browser": send_browser_notification,
}

logger = logging.getLogger("checkarr.alerting")

BATCH_WINDOW_SECONDS = 10

_pending_lock = asyncio.Lock()
_pending: list[tuple[str, str, str]] = []
_batch_task: asyncio.Task | None = None

# Channel ids that failed a send since the last housekeeping run drained
# this set (see housekeeping.flush_channel_failures) - a plain thread-safe
# set rather than anything persisted, since dispatch_alert runs off the
# event loop (asyncio.to_thread) and this only needs to survive until the
# next 30-minute housekeeping tick, not a restart.
_failed_channel_lock = threading.Lock()
_failed_channels: set[int] = set()


def pop_failed_channels() -> set[int]:
    with _failed_channel_lock:
        failed = set(_failed_channels)
        _failed_channels.clear()
    return failed


def send_via_channel(channel: models.NotificationChannel, subject: str, body: str) -> None:
    sender = _SENDERS.get(channel.type)
    if not sender:
        raise ValueError(f"Unknown notification channel type '{channel.type}'")
    sender(channel, subject, body)


def dispatch_alert(tier: str, subject: str, body: str) -> None:
    """tier is 'warn' or 'fail' - matches notify_on_warn/notify_on_fail.
    Called only from queue_alert's flush below - see this module's
    docstring for why nothing calls it directly anymore."""
    db = SessionLocal()
    try:
        channels = db.query(models.NotificationChannel).filter_by(enabled=True).all()
        for channel in channels:
            if tier == "warn" and not channel.notify_on_warn:
                continue
            if tier == "fail" and not channel.notify_on_fail:
                continue
            try:
                send_via_channel(channel, subject, body)
            except Exception:
                logger.exception("Failed to send alert via channel '%s' (%s)", channel.name, channel.id)
                with _failed_channel_lock:
                    _failed_channels.add(channel.id)
    finally:
        db.close()


async def queue_alert(tier: str, subject: str, body: str) -> None:
    """Holds the alert for BATCH_WINDOW_SECONDS, joining whatever else
    fires in the same window into a single combined send (see
    _flush_after_delay). Starts a fresh window if none is currently open;
    otherwise just joins the one already counting down - so a burst of
    alerts within the window always waits for that same window's flush,
    never opens a second overlapping one."""
    global _batch_task
    async with _pending_lock:
        _pending.append((tier, subject, body))
        if _batch_task is None or _batch_task.done():
            _batch_task = asyncio.create_task(_flush_after_delay())


async def _flush_after_delay() -> None:
    await asyncio.sleep(BATCH_WINDOW_SECONDS)
    async with _pending_lock:
        batch, _pending[:] = list(_pending), []
    if not batch:
        return
    tier = "fail" if any(t == "fail" for t, _, _ in batch) else "warn"
    if len(batch) == 1:
        _, subject, body = batch[0]
    else:
        subject = "Checkarr: Multiple alerts"
        body = "\n\n".join(f"{s}\n{b}" for _, s, b in batch)
    await asyncio.to_thread(dispatch_alert, tier, subject, body)
