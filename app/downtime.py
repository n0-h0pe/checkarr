"""Scheduled Down Time: evaluates whether an outbound alert (see
alerting.dispatch_alert) should be suppressed right now for a given service
and severity tier, per whatever DowntimeSchedules are enabled and linked
(via ServiceGroup) to that service. Suppression only ever gates the alert
dispatch - check results, the Notifications tab, and the dashboard are
completely unaffected.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import models


def _as_aware(dt: datetime) -> datetime:
    """SQLite round-trips DateTime columns as naive; treat naive as UTC -
    same convention as poller.py's _as_aware."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _date_matches(schedule: models.DowntimeSchedule, d: date) -> bool:
    """Whether `d` is a day this recurring schedule's window would start on
    - daily matches every day, weekly/monthly/yearly match the pattern
    carried in start_at's date component (see DowntimeSchedule's docstring).
    Bounded below by start_at's own date (the rule isn't active before it
    was created to start) and above by repeat_until, if set."""
    start_date = _as_aware(schedule.start_at).date()
    if d < start_date:
        return False
    if schedule.repeat_until and d > schedule.repeat_until:
        return False

    if schedule.recurrence == "daily":
        return True
    if schedule.recurrence == "weekly":
        return d.weekday() == start_date.weekday()
    if schedule.recurrence == "monthly":
        return d.day == start_date.day
    if schedule.recurrence == "yearly":
        return (d.month, d.day) == (start_date.month, start_date.day)
    return False


def _schedule_active(schedule: models.DowntimeSchedule, now: datetime) -> bool:
    start_at = _as_aware(schedule.start_at)
    end_at = _as_aware(schedule.end_at)

    if schedule.recurrence == "once":
        return start_at <= now <= end_at

    duration = end_at - start_at
    start_time = start_at.timetz()
    # Two candidate occurrence dates - today's and yesterday's - covers a
    # window that started yesterday and is still running past midnight into
    # today (e.g. a nightly 22:00-06:00 window). Anything longer than 24h on
    # a recurring schedule is a corner case "once" schedules already cover.
    for candidate in (now.date(), now.date() - timedelta(days=1)):
        if not _date_matches(schedule, candidate):
            continue
        occ_start = datetime.combine(candidate, start_time)
        occ_end = occ_start + duration
        if occ_start <= now <= occ_end:
            return True
    return False


def _applies_to_service(db: Session, schedule: models.DowntimeSchedule, service_id: int) -> bool:
    group_ids = [g.group_id for g in schedule.groups]
    if not group_ids:
        return False
    groups = db.query(models.ServiceGroup).filter(models.ServiceGroup.id.in_(group_ids)).all()
    for group in groups:
        if group.is_default:
            return True
        if (
            db.query(models.ServiceGroupMember)
            .filter_by(group_id=group.id, service_id=service_id)
            .first()
        ):
            return True
    return False


def is_suppressed(db: Session, service_id: int, tier: str, now: datetime) -> bool:
    """tier is 'warn' or 'fail', matching alerting.dispatch_alert's tiers."""
    query = db.query(models.DowntimeSchedule).filter_by(enabled=True)
    if tier == "warn":
        query = query.filter_by(suppress_warn=True)
    else:
        query = query.filter_by(suppress_fail=True)

    for schedule in query.all():
        if _schedule_active(schedule, now) and _applies_to_service(db, schedule, service_id):
            return True
    return False
