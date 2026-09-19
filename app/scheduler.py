import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import settings
from .database import SessionLocal
from .housekeeping import run_housekeeping
from .log_pruning import prune_all_services_async
from .models import Service
from .poller import poll_service

logger = logging.getLogger("checkarr.scheduler")

scheduler = AsyncIOScheduler()
HOUSEKEEPING_JOB_ID = "housekeeping"
HOUSEKEEPING_INTERVAL_MINUTES = 30
PRUNE_JOB_ID = "check-history-pruning"
# Separate from HOUSEKEEPING_INTERVAL_MINUTES above on purpose: pruning is a
# bulk DELETE, worth doing less often than the disk-space/notification-
# channel self-checks housekeeping still runs every 30 minutes - those are
# cheap reads where a fast reaction (e.g. to low disk space) actually
# matters, pruning isn't.
PRUNE_INTERVAL_HOURS = 6


def _job_id(service_id: int) -> str:
    return f"poll-service-{service_id}"


def schedule_service(service: Service) -> None:
    """One APScheduler job per enabled service, re-created (not just
    updated) on every call - the simplest way to pick up a changed interval
    or name after an edit, since there's no cheap partial-update API for an
    existing job's trigger. Called after every service create/update
    (including disabling one, which routes here and hits the early return
    below) and once per service at startup (see reschedule_all).

    `max_instances=1` + `coalesce=True`: if a poll ever runs long enough to
    still be going when the next one's due (a slow/hanging check), skip
    queuing a pileup of overlapping runs - just wait for the current one
    and then run once, not once-per-missed-tick. `misfire_grace_time=60`
    forgives the scheduler itself being briefly blocked (e.g. by another
    service's poll) without treating a tick that starts a few seconds late
    as missed entirely. `next_run_time=datetime.now()` fires an immediate
    first poll on creation, rather than waiting a full interval to find out
    whether a newly added service is even reachable.
    """
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
    """Rebuilds every service's job from scratch - called once at startup
    (see start() below), since APScheduler's own job store isn't persisted
    across restarts here (an in-memory scheduler, not one of the
    SQLAlchemy/Redis-backed job stores APScheduler also supports)."""
    db = SessionLocal()
    try:
        for service in db.query(Service).all():
            schedule_service(service)
    finally:
        db.close()


def schedule_housekeeping() -> None:
    """Adds/replaces the job that runs Checkarr's own self-monitoring (see
    housekeeping.run_housekeeping - checking free disk space, checking for
    failing notification channels) on a flat 30-minute interval. Fixed, not
    user-configurable - there's no time-of-day to get right here, just
    "check regularly." Also fires once immediately (`next_run_time=now`) so
    a freshly started container doesn't wait up to 30 minutes for its first
    run. Check history pruning used to run as part of this same job; see
    schedule_pruning below for why it's now separate."""
    scheduler.add_job(
        run_housekeeping,
        trigger=IntervalTrigger(minutes=HOUSEKEEPING_INTERVAL_MINUTES),
        id=HOUSEKEEPING_JOB_ID,
        name="Checkarr housekeeping (self-monitoring)",
        replace_existing=True,
        next_run_time=datetime.now(),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )


def schedule_pruning() -> None:
    """Adds/replaces the job that deletes expired CheckResult rows (see
    log_pruning.prune_all_services, Settings > Check History Pruning's
    `retention_days`) on a flat interval, same "just check regularly, no
    time-of-day" reasoning as schedule_housekeeping above - just a longer
    one (PRUNE_INTERVAL_HOURS), since a bulk DELETE is worth doing less
    often than the cheap reads housekeeping's own job covers. Also fires
    once immediately so a freshly started container's retention setting
    takes effect right away rather than after up to
    PRUNE_INTERVAL_HOURS hours."""
    scheduler.add_job(
        prune_all_services_async,
        trigger=IntervalTrigger(hours=PRUNE_INTERVAL_HOURS),
        id=PRUNE_JOB_ID,
        name="Checkarr check history pruning",
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
    schedule_pruning()


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
