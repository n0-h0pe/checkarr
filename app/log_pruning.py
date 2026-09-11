"""Deletes old CheckResult rows across every service, on the one daily
schedule configured in Settings > Log Pruning (see LogPruningSettings,
scheduler.schedule_log_pruning). Replaces the old per-poll-per-service
pruning that used to live in poller.py - one job, one configurable time and
retention, instead of an env-var-fixed cutoff applied after every poll.
"""

import logging
from datetime import datetime, timedelta, timezone

from .database import SessionLocal
from .models import CheckResult, LogPruningSettings
from .queries import get_or_create_log_pruning_settings

logger = logging.getLogger("healthchecker.log_pruning")


def _as_aware(dt: datetime) -> datetime:
    """SQLite round-trips DateTime columns as naive; treat naive as UTC -
    same convention as poller.py/downtime.py's _as_aware."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def prune_all_services(db=None) -> int:
    """Deletes every CheckResult row older than the configured retention,
    across all services, and records when this ran. Opens its own session
    when called bare as a scheduler job (mirrors alerting.dispatch_alert);
    accepts an existing one for callers (e.g. the manual "Prune now" route)
    that already have one open."""
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        settings_row = get_or_create_log_pruning_settings(db)
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings_row.retention_days)
        deleted = (
            db.query(CheckResult)
            .filter(CheckResult.timestamp < cutoff)
            .delete(synchronize_session=False)
        )
        settings_row.last_pruned_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("Pruned %s check result row(s) older than %s day(s)", deleted, settings_row.retention_days)
        return deleted
    finally:
        if own_session:
            db.close()


def most_recent_scheduled_occurrence(settings_row: LogPruningSettings, now: datetime) -> datetime:
    """The latest UTC datetime <= now at which the configured daily prune
    time falls - today's, or yesterday's if today's hasn't happened yet."""
    candidate = now.replace(hour=settings_row.prune_hour, minute=settings_row.prune_minute, second=0, microsecond=0)
    if candidate > now:
        candidate -= timedelta(days=1)
    return candidate


def catch_up_if_needed(db=None) -> None:
    """Called once at startup, after the recurring job is scheduled: if the
    configured prune time already passed since the last prune (the
    container was offline at 2am, say), prunes immediately instead of
    waiting up to 24h for the next scheduled run. Independent of
    APScheduler's own misfire window, which only covers a process that was
    merely paused briefly, not off for hours or days."""
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        settings_row = get_or_create_log_pruning_settings(db)
        now = datetime.now(timezone.utc)
        scheduled = most_recent_scheduled_occurrence(settings_row, now)
        last = settings_row.last_pruned_at
        if last is None or _as_aware(last) < scheduled:
            logger.info("Log pruning missed its last scheduled run - catching up now")
            prune_all_services(db)
    finally:
        if own_session:
            db.close()
