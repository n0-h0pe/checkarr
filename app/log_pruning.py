"""Deletes old CheckResult rows ("Log & History", see Settings > Log &
History Pruning / LogPruningSettings) across every service. Called every 30
minutes by housekeeping.run_housekeeping (see scheduler.schedule_housekeeping)
- just deletes whatever currently qualifies, no time-of-day scheduling to
get right. Replaces the old per-poll-per-service pruning that used to live
in poller.py.
"""

import logging
from datetime import datetime, timedelta, timezone

from .database import SessionLocal
from .models import CheckResult
from .queries import get_or_create_log_pruning_settings

logger = logging.getLogger("checkarr.log_pruning")


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
