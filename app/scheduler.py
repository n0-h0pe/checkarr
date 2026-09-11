import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import settings
from .database import SessionLocal
from .log_pruning import catch_up_if_needed, prune_all_services
from .models import Service
from .poller import poll_service
from .queries import get_or_create_log_pruning_settings

logger = logging.getLogger("healthchecker.scheduler")

scheduler = AsyncIOScheduler()
PRUNE_JOB_ID = "prune-logs"


def _job_id(service_id: int) -> str:
    return f"poll-service-{service_id}"


def schedule_service(service: Service) -> None:
    job_id = _job_id(service.id)
    scheduler.remove_job(job_id) if scheduler.get_job(job_id) else None

    if not service.enabled:
        return

    interval = service.poll_interval_seconds or settings.default_poll_interval_seconds
    scheduler.add_job(
        poll_service,
        trigger=IntervalTrigger(seconds=interval),
        args=[service.id],
        id=job_id,
        name=f"Poll {service.name}",
        replace_existing=True,
        next_run_time=datetime.now(),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )


def unschedule_service(service_id: int) -> None:
    job_id = _job_id(service_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)


def reschedule_all() -> None:
    db = SessionLocal()
    try:
        for service in db.query(Service).all():
            schedule_service(service)
    finally:
        db.close()


def schedule_log_pruning(days: int, hour: int, minute: int) -> None:
    """Adds/replaces the job that deletes old CheckResult rows across every
    service, once every `days` days at the given UTC time - not daily
    regardless of the configured retention (a CronTrigger would fire every
    day no matter what the user set the day count to). Called at startup
    with the stored schedule, and again by the Log Pruning settings PUT
    route whenever the user changes it, so a change takes effect
    immediately without a restart.

    The next firing is anchored to the next occurrence of the given time
    from right now, then repeats every `days` days from there - so changing
    the schedule always lands on the configured time of day, it just resets
    which day that next falls on. Always in UTC regardless of the
    container's own timezone - the frontend already converts the user's
    local time to UTC hour/minute before saving."""
    now = datetime.now(timezone.utc)
    start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if start <= now:
        start += timedelta(days=1)
    scheduler.add_job(
        prune_all_services,
        trigger=IntervalTrigger(days=max(1, days), start_date=start, timezone=timezone.utc),
        id=PRUNE_JOB_ID,
        name="Prune old check history",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )


def start() -> None:
    if not scheduler.running:
        scheduler.start()
    reschedule_all()

    db = SessionLocal()
    try:
        settings_row = get_or_create_log_pruning_settings(db)
        schedule_log_pruning(settings_row.retention_days, settings_row.prune_hour, settings_row.prune_minute)
    finally:
        db.close()
    # After the recurring job is in place, not before - catching up here
    # only backfills a missed run, it doesn't need to race the schedule.
    catch_up_if_needed()


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
