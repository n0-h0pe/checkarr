import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import settings
from .database import SessionLocal
from .housekeeping import run_housekeeping
from .models import Service
from .poller import poll_service

logger = logging.getLogger("checkarr.scheduler")

scheduler = AsyncIOScheduler()
HOUSEKEEPING_JOB_ID = "housekeeping"
HOUSEKEEPING_INTERVAL_MINUTES = 30


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


def schedule_housekeeping() -> None:
    """Adds/replaces the job that runs Checkarr's own upkeep (see
    housekeeping.run_housekeeping - pruning old history, checking free disk
    space, checking for failing notification channels) on a flat 30-minute
    interval. Fixed, not user-configurable - there's no time-of-day to get
    right here, just "check regularly." Also fires once immediately
    (`next_run_time=now`) so a freshly started container doesn't wait up to
    30 minutes for its first run."""
    scheduler.add_job(
        run_housekeeping,
        trigger=IntervalTrigger(minutes=HOUSEKEEPING_INTERVAL_MINUTES),
        id=HOUSEKEEPING_JOB_ID,
        name="Checkarr housekeeping (log/history pruning, self-monitoring)",
        replace_existing=True,
        next_run_time=datetime.now(),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )


def start() -> None:
    if not scheduler.running:
        scheduler.start()
    reschedule_all()
    schedule_housekeeping()


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
