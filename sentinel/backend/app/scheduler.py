"""Background schedule for the RBI sync."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.agents.pipeline import run_summary_queue, run_sync

log = logging.getLogger("sentinel.scheduler")
scheduler = AsyncIOScheduler(timezone=timezone.utc)
JOB_ID = "rbi_sync"


async def _job() -> None:
    await run_sync(trigger="schedule", actor="scheduler")


def start(interval_minutes: int, run_soon: bool) -> None:
    extra = {"next_run_time": datetime.now(timezone.utc) + timedelta(seconds=8)} if run_soon else {}
    scheduler.add_job(
        _job,
        IntervalTrigger(minutes=interval_minutes, timezone=timezone.utc),
        id=JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        **extra,  # passing next_run_time=None would add the job paused
    )
    from app.config import get_settings

    s = get_settings()
    if s.ai_summary_queue_enabled:
        scheduler.add_job(
            run_summary_queue,
            IntervalTrigger(minutes=s.ai_summary_interval_minutes, timezone=timezone.utc),
            id="ai_summary_queue",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(minutes=2),
        )
    scheduler.start()
    log.info("scheduler started", extra={"interval_minutes": interval_minutes, "run_soon": run_soon})


def reschedule(interval_minutes: int) -> None:
    if scheduler.get_job(JOB_ID):
        scheduler.reschedule_job(JOB_ID, trigger=IntervalTrigger(minutes=interval_minutes, timezone=timezone.utc))
        log.info("sync rescheduled", extra={"interval_minutes": interval_minutes})


def next_run() -> str | None:
    job = scheduler.get_job(JOB_ID) if scheduler.running else None
    return job.next_run_time.isoformat() if job and job.next_run_time else None


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
