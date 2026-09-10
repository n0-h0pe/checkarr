import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone

import httpx

from .checks.base import NotificationItem
from .checks.runner import SERVICE_SCOPED_TYPES, run_check
from .config import settings
from .database import SessionLocal
from .models import CheckDefinition, CheckResult, Notification, Service

logger = logging.getLogger("healthchecker.poller")


def _fingerprint(item: NotificationItem) -> str:
    return hashlib.sha256(f"{item.source}:{item.message}".encode()).hexdigest()


def _as_aware(dt: datetime) -> datetime:
    """SQLite round-trips DateTime columns as naive; treat naive as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _due_checks(db, checks: list[CheckDefinition], now: datetime) -> list[CheckDefinition]:
    """Filters to checks whose own interval override has actually elapsed.

    Checks without an override run on every tick (the service's own poll
    cadence). One with e.g. interval_seconds=600 on a service polled every
    5 minutes simply gets skipped on every other tick, reusing its last
    stored result in between.
    """
    due = []
    for check in checks:
        if not check.interval_seconds:
            due.append(check)
            continue
        last = (
            db.query(CheckResult)
            .filter(CheckResult.check_id == check.id)
            .order_by(CheckResult.timestamp.desc())
            .first()
        )
        if not last or (now - _as_aware(last.timestamp)).total_seconds() >= check.interval_seconds:
            due.append(check)
    return due


async def poll_service(service_id: int) -> None:
    db = SessionLocal()
    try:
        service = db.get(Service, service_id)
        if not service or not service.enabled:
            return

        checks = [c for c in service.checks if c.enabled]
        if not checks:
            return

        now = datetime.now(timezone.utc)
        due = _due_checks(db, checks, now)
        if not due:
            return

        targets = service.get_targets()
        suffix_targets = len(targets) > 1  # only disambiguate when both local+remote are configured

        jobs: list[tuple[CheckDefinition, str | None, str | None]] = []  # (check, label, base_url)
        for check in due:
            if check.type in SERVICE_SCOPED_TYPES:
                jobs.append((check, None, None))
            elif targets:
                for label, url in targets:
                    jobs.append((check, label, url))
            else:
                # Target-scoped check on a service with no address configured
                # (shouldn't normally happen - validated at creation).
                jobs.append((check, None, None))

        try:
            async with httpx.AsyncClient(
                timeout=settings.http_timeout_seconds, verify=service.verify_ssl
            ) as client:
                outcomes = await asyncio.gather(*(run_check(client, service, c, url) for c, _, url in jobs))
        except Exception:
            logger.exception("Unexpected error polling service %s (%s)", service.name, service.id)
            return

        notification_sources_checked: set[str] = set()
        fingerprints_seen: set[str] = set()

        for (check, label, _url), outcome in zip(jobs, outcomes):
            check_name = f"{check.name} ({label})" if label and suffix_targets else check.name
            db.add(
                CheckResult(
                    service_id=service.id,
                    check_id=check.id,
                    check_name=check_name,
                    check_type=check.type,
                    status=outcome.status,
                    message=outcome.message,
                    response_time_ms=outcome.response_time_ms,
                    timestamp=now,
                )
            )
            if check.type == "arr_health":
                notification_sources_checked.add(f"{service.type}_health")

            for item in outcome.notifications:
                fp = _fingerprint(item)
                fingerprints_seen.add(fp)
                existing = (
                    db.query(Notification)
                    .filter_by(service_id=service.id, fingerprint=fp, resolved=False)
                    .first()
                )
                if existing:
                    existing.last_seen = now
                    existing.severity = item.severity
                else:
                    db.add(
                        Notification(
                            service_id=service.id,
                            source=item.source,
                            fingerprint=fp,
                            severity=item.severity,
                            message=item.message,
                            wiki_url=item.wiki_url,
                            first_seen=now,
                            last_seen=now,
                        )
                    )

        if notification_sources_checked:
            stale = (
                db.query(Notification)
                .filter(
                    Notification.service_id == service.id,
                    Notification.source.in_(notification_sources_checked),
                    Notification.resolved.is_(False),
                )
                .all()
            )
            for notif in stale:
                if notif.fingerprint not in fingerprints_seen:
                    notif.resolved = True
                    notif.resolved_at = now

        db.commit()
        _prune_old_results(db, service.id)
    finally:
        db.close()


def _prune_old_results(db, service_id: int) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.history_retention_days)
    db.query(CheckResult).filter(
        CheckResult.service_id == service_id, CheckResult.timestamp < cutoff
    ).delete(synchronize_session=False)
    db.commit()
