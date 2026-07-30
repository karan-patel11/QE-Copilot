"""Celery beat schedule (ADR-0004).

Reuses the worker's Celery app and task definitions so the scheduler and worker
never diverge. The one registered tick stamps the heartbeat the System Health
API reads; feature schedules arrive with their features.
"""

from __future__ import annotations

from celery.schedules import crontab

from qe_observability import configure_logging, get_logger
from qe_worker.celery_app import celery_app

configure_logging()
logger = get_logger("qe_scheduler.beat")

# Periodic schedule. The heartbeat is what the System Health API reads as
# scheduler liveness (ADR-0109); it supersedes the Phase 0 no-op tick, which
# proved the same broker path without recording anything.
celery_app.conf.beat_schedule = {
    "scheduler-heartbeat-every-minute": {
        "task": "qe_worker.scheduler_heartbeat",
        "schedule": crontab(minute="*"),
    },
}
# TODO(phase-4+): register real recurring jobs (nightly regeneration, ...) here.


@celery_app.on_after_configure.connect  # type: ignore[misc]
def _log_scheduler_ready(sender: object, **_: object) -> None:
    """Emit one structured line so 'scheduler ticks' is observable in logs."""
    logger.info("scheduler beat configured; heartbeat tick scheduled")


__all__ = ["celery_app"]
