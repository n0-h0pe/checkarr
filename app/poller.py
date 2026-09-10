import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone

import httpx

from .checks.base import NotificationItem
from .checks.runner import run_check
from .config import settings
from .database import SessionLocal
from .models import CheckResult, Notification, Service

logger = logging.getLogger("healthchecker.poller")


def _fingerprint(item: NotificationItem) -> str:
    return hashlib.sha256(f"{item.source}:{item.message}".encode()).hexdigest()


async def poll_service(service_id: int) -> None:
    db = SessionLocal()
    try:
        service = db.get(Service, service_id)
        if not service or not service.enabled:
            return

        checks = [c for c in service.checks if c.enabled]
        if not checks:
            return

        try:
            async with httpx.AsyncClient(
                timeout=settings.http_timeout_seconds, verify=service.verify_ssl
            ) as client:
                outcomes = await asyncio.gather(*(run_check(client, service, c) for c in checks))
        except Exception:
            logger.exception("Unexpected error polling service %s (%s)", service.name, service.id)
            return

        now = datetime.now(timezone.utc)
        notification_sources_checked: set[str] = set()
        fingerprints_seen: set[str] = set()

        for check, outcome in zip(checks, outcomes):
            db.add(
                CheckResult(
                    service_id=service.id,
                    check_id=check.id,
                    check_name=check.name,
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
