import asyncio
import hashlib
import logging
from datetime import datetime, timezone

import httpx

from .alerting import queue_alert
from .checks.base import STATUS_FAIL, STATUS_WARN, NotificationItem
from .checks.runner import ALWAYS_BOTH_TARGETS_TYPES, SERVICE_SCOPED_TYPES, run_check
from .config import settings
from .database import SessionLocal
from .downtime import is_suppressed
from .models import CheckDefinition, CheckResult, Notification, Service

# Notification.severity -> alert tier (see NotificationChannel.notify_on_warn/
# notify_on_fail). "notice"/"ok" are informational, not actionable - never
# alerted on.
_NOTIFICATION_SEVERITY_TIER = {"warning": "warn", "error": "fail"}

logger = logging.getLogger("checkarr.poller")


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
                continue
            if not targets:
                # Target-scoped check on a service with no address configured
                # (shouldn't normally happen - validated at creation).
                jobs.append((check, None, None))
                continue

            if check.type == "ssl_certificate":
                # Always every https target, regardless of check_both_targets
                # - unlike the "both" toggle below (which is about not
                # doubling up API-heavy checks), a cert check against a
                # non-https address isn't a second useful data point, it's
                # meaningless, so it's excluded rather than included.
                selected = [t for t in targets if t[1].lower().startswith("https://")]
            elif suffix_targets and not service.check_both_targets and check.type not in ALWAYS_BOTH_TARGETS_TYPES:
                # Default when both addresses are set: everything except the
                # web UI check runs against the local address only.
                selected = [t for t in targets if t[0] == "local"] or targets
            else:
                selected = targets

            for label, url in selected:
                jobs.append((check, label, url))

        try:
            # verify=False: ordinary checks no longer enforce cert trust at
            # all (self-signed local HTTPS just works) - the dedicated
            # ssl_certificate check (checks/ssl_check.py) does its own real,
            # strict validation independently and is the one place cert
            # problems get reported.
            async with httpx.AsyncClient(
                timeout=settings.http_timeout_seconds, verify=False
            ) as client:
                outcomes = await asyncio.gather(*(run_check(client, service, c, url) for c, _, url in jobs))
        except Exception:
            logger.exception("Unexpected error polling service %s (%s)", service.name, service.id)
            return

        notification_sources_checked: set[str] = set()
        fingerprints_seen: set[str] = set()
        # (tier, subject, body) queued while the loop still has a DB session
        # open for "what was the previous status" lookups - actually sent
        # after commit, below, so a rolled-back poll can never fire a false
        # alert.
        alerts_to_send: list[tuple[str, str, str]] = []

        for (check, label, _url), outcome in zip(jobs, outcomes):
            check_name = f"{check.name} ({label})" if label and suffix_targets else check.name
            status = outcome.status
            # "Alert level" (any check type) caps how loud a failure reports
            # as - doesn't touch OK/WARN outcomes, only downgrades a FAIL.
            if status == STATUS_FAIL and (check.config or {}).get("alert_level") == "warn":
                status = STATUS_WARN

            # Recorded on this result permanently, not reconstructed later
            # from whatever schedules happen to still exist when History is
            # viewed - see CheckResult.in_sdt's docstring. Checked on every
            # warn/fail result, not just ones that go on to trigger a new
            # alert below - an ongoing, already-alerted issue still needs an
            # accurate in_sdt on every poll while it continues.
            in_sdt = False
            suppressed_by_threshold = False
            if status in (STATUS_WARN, STATUS_FAIL):
                tier = "warn" if status == STATUS_WARN else "fail"
                in_sdt = is_suppressed(db, service.id, tier, now)

                # "Alert after" (config.alert_after_count, default 1) - how
                # many consecutive results of this exact status (this one
                # included) are needed before it's worth alerting on at all.
                # Fetching exactly `threshold` prior results (not more) is
                # deliberate: it's just enough to tell "the streak, including
                # this result, is exactly `threshold` long" (fire once) apart
                # from "already longer than that" (already fired earlier,
                # stay quiet) without needing to know the streak's full
                # length beyond that point.
                threshold = max(1, int((check.config or {}).get("alert_after_count") or 1))
                streak = 1
                if threshold > 1:
                    prior_results = (
                        db.query(CheckResult)
                        .filter(CheckResult.check_id == check.id)
                        .order_by(CheckResult.timestamp.desc())
                        .limit(threshold)
                        .all()
                    )
                    for prior in prior_results:
                        if prior.status == status:
                            streak += 1
                        else:
                            break

                suppressed_by_threshold = streak < threshold
                # Alerts exactly once, the moment the streak first reaches
                # the threshold - streak == threshold rather than >= is what
                # keeps this from re-alerting on every later poll while the
                # same status continues (same "only on transition" idea the
                # old previous.status != status check used, generalized from
                # "streak of 1" to "streak of N").
                if streak == threshold:
                    alerts_to_send.append(
                        (tier, f"[Checkarr] {service.name} - {check_name}: {status.upper()}", outcome.message)
                    )

            db.add(
                CheckResult(
                    service_id=service.id,
                    check_id=check.id,
                    check_name=check_name,
                    check_type=check.type,
                    status=status,
                    message=outcome.message,
                    response_time_ms=outcome.response_time_ms,
                    timestamp=now,
                    in_sdt=in_sdt,
                    suppressed_by_threshold=suppressed_by_threshold,
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
                    tier = _NOTIFICATION_SEVERITY_TIER.get(item.severity)
                    if tier:
                        alerts_to_send.append((tier, f"[Checkarr] {service.name} - {item.source}", item.message))

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

        for tier, subject, body in alerts_to_send:
            # Scheduled Down Time only ever gates this dispatch - the check
            # result/notification above was already recorded normally either
            # way, so the dashboard and Notifications tab are unaffected.
            if is_suppressed(db, service.id, tier, now):
                continue
            # Fire-and-forget: queue_alert holds this for a 10s coalescing
            # window (see alerting.py) before it and anything else that
            # fires in that window are sent as one combined alert - never
            # blocks or fails the poll loop itself.
            asyncio.create_task(queue_alert(tier, subject, body))
    finally:
        db.close()
