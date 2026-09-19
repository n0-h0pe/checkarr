"""The recurring background job (every 30 minutes, see
scheduler.schedule_housekeeping) that watches Checkarr's own health: free
disk space on /config, and notification channels that have started failing
to send. Self-monitoring alerts go through the same queue_alert batching
pipeline as ordinary check alerts (see alerting.py) - so a channel that's
broken can't flood itself with "you're broken" alerts any more than a
flapping service can flood it with ordinary ones.

Check history pruning (log_pruning.py) used to run as part of this same
job; it's now its own job on a longer interval (see
scheduler.schedule_pruning) since a bulk DELETE doesn't need the same
30-minute cadence these cheap reads benefit from.
"""

import asyncio
import logging
import shutil

from . import alerting
from .config import settings
from .database import SessionLocal
from .queries import get_or_create_self_monitoring_state

logger = logging.getLogger("checkarr.housekeeping")

DISK_SPACE_WARN_BYTES = 100 * 1024 * 1024
DISK_SPACE_FAIL_BYTES = 10 * 1024 * 1024


async def run_housekeeping() -> None:
    await check_disk_space()
    await flush_channel_failures()


async def check_disk_space() -> None:
    free_bytes = (await asyncio.to_thread(shutil.disk_usage, settings.data_path)).free
    if free_bytes < DISK_SPACE_FAIL_BYTES:
        tier = "fail"
    elif free_bytes < DISK_SPACE_WARN_BYTES:
        tier = "warn"
    else:
        tier = None

    def _read_and_update() -> str | None:
        db = SessionLocal()
        try:
            state = get_or_create_self_monitoring_state(db)
            previous = state.disk_space_tier
            if state.disk_space_tier != tier:
                state.disk_space_tier = tier
                db.commit()
            return previous
        finally:
            db.close()

    previous_tier = await asyncio.to_thread(_read_and_update)
    if tier == previous_tier:
        return  # no transition - don't re-alert every cycle while it stays the same

    free_mb = free_bytes / (1024 * 1024)
    if tier is None:
        logger.info("Free disk space on /config recovered (%.1f MB free)", free_mb)
        return
    await alerting.queue_alert(
        tier,
        "[Checkarr] Low disk space on /config",
        f"Only {free_mb:.1f} MB free on {settings.data_path} - Checkarr's own database and config "
        "volume is running low. Free up space or grow the volume.",
    )


async def flush_channel_failures() -> None:
    failed_ids = alerting.pop_failed_channels()
    if not failed_ids:
        return

    def _names() -> list[str]:
        db = SessionLocal()
        try:
            from . import models

            rows = db.query(models.NotificationChannel).filter(models.NotificationChannel.id.in_(failed_ids)).all()
            return [c.name for c in rows]
        finally:
            db.close()

    names = await asyncio.to_thread(_names)
    if not names:
        return
    await alerting.queue_alert(
        "warn",
        "[Checkarr] Notification channel failing",
        "The following notification channel(s) failed to send at least one alert since the last "
        "check: " + ", ".join(names) + ". Check their settings (server address, credentials).",
    )
