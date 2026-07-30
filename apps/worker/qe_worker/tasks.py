"""Worker tasks.

Phase 0 ships only a no-op health task so the worker path (enqueue -> execute
-> result) can be exercised end-to-end. Real tasks (test generation, triage,
ingestion) arrive in later phases.
"""

from __future__ import annotations

from typing import Any

from qe_common.jobs import JobState
from qe_observability import bind_log_context, configure_logging, get_logger
from qe_worker.celery_app import celery_app

configure_logging()
logger = get_logger("qe_worker.tasks")


@celery_app.task(name="qe_worker.health_check")  # type: ignore[misc]
def health_check() -> dict[str, Any]:
    """No-op task that returns a completed job envelope.

    TODO(phase-1): replace with real, persisted job execution.
    """
    bind_log_context(event_type="worker.health_check")
    logger.info("worker health check executed")
    return {"status": "ok", "state": JobState.COMPLETED.value}


__all__ = ["health_check"]
