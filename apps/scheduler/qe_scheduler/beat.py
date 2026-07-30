"""Celery beat schedule (ADR-0004).

Reuses the worker's Celery app and task definitions so the scheduler and worker
never diverge. Phase 0 registers a single periodic no-op tick that enqueues the
worker health check; real periodic jobs arrive in later phases.
"""

from __future__ import annotations

from celery.schedules import crontab

from qe_observability import configure_logging, get_logger
from qe_worker.celery_app import celery_app

configure_logging()
logger = get_logger("qe_scheduler.beat")

# Periodic schedule. TODO(phase-1+): register real recurring jobs here.
celery_app.conf.beat_schedule = {
    "health-tick-every-minute": {
        "task": "qe_worker.health_check",
        "schedule": crontab(minute="*"),
    },
}


@celery_app.on_after_configure.connect  # type: ignore[misc]
def _log_scheduler_ready(sender: object, **_: object) -> None:
    """Emit one structured line so 'scheduler ticks' is observable in logs."""
    logger.info("scheduler beat configured; health tick scheduled")


__all__ = ["celery_app"]
