"""Dispatches outbound alerts (Settings > Push Notifications) to every
enabled channel opted into the given severity tier. Adding a new channel
type later (Discord, Pushbullet, ...) means one new function in
app/notifiers/ and one branch in send_via_channel below - see
NOTIFICATION_CHANNEL_TYPE_META in routers/meta.py for the matching
frontend-config side of that.

Called fire-and-forget from poller.py via asyncio.to_thread (this whole
module is sync - it opens its own DB session rather than sharing the
poller's, and does blocking network I/O per channel), so a slow or broken
channel can never block or fail a poll.
"""

import logging

from . import models
from .database import SessionLocal
from .notifiers.email import send_email

logger = logging.getLogger("healthchecker.alerting")


def send_via_channel(channel: models.NotificationChannel, subject: str, body: str) -> None:
    if channel.type == "email":
        send_email(channel, subject, body)
    else:
        raise ValueError(f"Unknown notification channel type '{channel.type}'")


def dispatch_alert(tier: str, subject: str, body: str) -> None:
    """tier is 'warn' or 'fail' - matches notify_on_warn/notify_on_fail."""
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
    finally:
        db.close()
