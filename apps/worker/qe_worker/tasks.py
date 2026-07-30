"""Worker tasks.

``run_job`` is the executor behind every asynchronous API request: it claims the
queued row, drives it through the state machine, and persists each transition,
so the ``jobs`` table — not the broker — is the source of truth (ADR-0107).
"""

from __future__ import annotations

import datetime as _dt
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from qe_common.jobs import JobKind, JobState, assert_transition
from qe_database.models import Job
from qe_database.session import get_engine
from qe_observability import bind_log_context, configure_logging, get_logger
from qe_worker.celery_app import celery_app

configure_logging()
logger = get_logger("qe_worker.tasks")


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def _handle_health_check(job: Job) -> dict[str, Any]:
    """The Phase 1 job kind: proves the whole path without doing real work."""
    return {
        "ok": True,
        "kind": job.kind,
        "echo": job.payload,
        "executed_at": _now().isoformat(),
    }


# One handler per executable kind. A kind with no handler fails the job loudly
# rather than silently completing with nothing done.
_HANDLERS: dict[str, Callable[[Job], dict[str, Any]]] = {
    JobKind.HEALTH_CHECK.value: _handle_health_check,
    # TODO(phase-3): knowledge ingestion  TODO(phase-4): test generation
    # TODO(phase-5): defect triage
}


def _claim(session: Session, job_id: uuid.UUID) -> Job | None:
    """Lock the job row and take it ``QUEUED -> RUNNING``.

    ``FOR UPDATE`` plus the state check makes this idempotent: a redelivered
    message finds the job no longer ``QUEUED`` and is dropped instead of running
    the work a second time.
    """
    job = session.execute(
        select(Job).where(Job.id == job_id).with_for_update()
    ).scalar_one_or_none()
    if job is None:
        logger.warning("job not found", extra={"event_type": "job.missing"})
        return None

    if job.job_state is not JobState.QUEUED:
        logger.warning(
            f"ignoring job in state {job.state}",
            extra={"event_type": "job.not_claimable"},
        )
        session.rollback()
        return None

    assert_transition(job.job_state, JobState.RUNNING)
    job.state = JobState.RUNNING.value
    job.started_at = _now()
    job.attempts += 1
    session.commit()
    return job


@celery_app.task(name="qe_worker.run_job")  # type: ignore[misc]
def run_job(job_id: str) -> dict[str, Any]:
    """Execute a persisted job, writing every state transition to the database."""
    bind_log_context(job_id=job_id, event_type="job.run")

    with Session(get_engine(), expire_on_commit=False) as session:
        job = _claim(session, uuid.UUID(job_id))
        if job is None:
            return {"job_id": job_id, "state": None, "claimed": False}

        bind_log_context(
            project_id=str(job.project_id) if job.project_id else None,
            user_id=str(job.created_by) if job.created_by else None,
        )
        handler = _HANDLERS.get(job.kind)
        try:
            if handler is None:
                raise ValueError(f"No handler is registered for job kind {job.kind!r}.")
            result = handler(job)
        except Exception as exc:
            assert_transition(job.job_state, JobState.FAILED)
            job.state = JobState.FAILED.value
            job.error = str(exc)
            job.finished_at = _now()
            session.commit()
            logger.error("job failed", exc_info=exc, extra={"event_type": "job.failed"})
            return {"job_id": job_id, "state": job.state, "claimed": True}

        assert_transition(job.job_state, JobState.COMPLETED)
        job.state = JobState.COMPLETED.value
        job.result = result
        job.finished_at = _now()
        session.commit()
        logger.info("job completed", extra={"event_type": "job.completed"})
        return {"job_id": job_id, "state": job.state, "claimed": True}


@celery_app.task(name="qe_worker.health_check")  # type: ignore[misc]
def health_check() -> dict[str, Any]:
    """Unpersisted liveness probe for the worker process itself.

    Distinct from a ``health_check`` *job*: this proves the broker → worker path
    without touching the database, which is what the scheduler tick and the
    System Health page rely on.
    """
    bind_log_context(event_type="worker.health_check")
    logger.info("worker health check executed")
    return {"status": "ok", "state": JobState.COMPLETED.value}


__all__ = ["health_check", "run_job"]
