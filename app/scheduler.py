import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
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


def schedule_log_pruning(hour: int, minute: int) -> None:
    """Adds/replaces the one daily job that deletes old CheckResult rows
    across every service - called at startup with the stored time, and
    again by the Log Pruning settings PUT route whenever the user changes
    it, so a new time takes effect immediately without a restart. Always in
    UTC regardless of the container's own timezone - the frontend already
    converts the user's local time to UTC hour/minute before saving."""
    scheduler.add_job(
        prune_all_services,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=timezone.utc),
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
        schedule_log_pruning(settings_row.prune_hour, settings_row.prune_minute)
    finally:
        db.close()
    # After the recurring job is in place, not before - catching up here
    # only backfills a missed run, it doesn't need to race the schedule.
    catch_up_if_needed()


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
