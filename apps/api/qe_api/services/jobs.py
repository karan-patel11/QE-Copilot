"""Job services: creation, dispatch to the queue, and read access.

The API only ever performs the ``PENDING -> QUEUED`` transition. Everything
after that belongs to the worker, which writes each transition to the same row
(ADR-0107), so a polling client reads authoritative state rather than whatever
the broker last reported.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from qe_api.services.audit import record_audit
from qe_api.services.projects import get_project
from qe_api.services.support import (
    commit_and_refresh,
    commit_or_conflict,
    flush_or_conflict,
)
from qe_auth import Permission, Principal
from qe_common.audit import AuditAction, AuditEntity
from qe_common.errors import JobNotFoundError, ServiceUnavailableError
from qe_common.jobs import JobKind, JobState, assert_transition
from qe_database.models import Job
from qe_observability import get_logger

logger = get_logger("qe_api.services.jobs")

# Name of the worker task, dispatched by name so the API never imports worker
# task code — only the broker configuration.
RUN_JOB_TASK = "qe_worker.run_job"


async def create_job(
    session: AsyncSession,
    principal: Principal,
    *,
    kind: JobKind,
    payload: dict[str, Any] | None = None,
    project_id: uuid.UUID | None = None,
) -> Job:
    """Persist a job, move it to ``QUEUED``, and dispatch it to the worker."""
    principal.require(Permission.JOB_CREATE)
    if project_id is not None:
        # 404s when the project is another tenant's, before anything is written.
        await get_project(session, principal, project_id)

    job = Job(
        organisation_id=principal.organisation_id,
        project_id=project_id,
        created_by=principal.user_id,
        kind=kind.value,
        state=JobState.PENDING.value,
        payload=payload or {},
    )
    session.add(job)
    await flush_or_conflict(session, "Job could not be created.")
    # ``kind`` only: a payload can carry arbitrary caller data and the audit
    # trail is not the place to duplicate it.
    await record_audit(
        session,
        principal,
        action=AuditAction.CREATE,
        entity_type=AuditEntity.JOB,
        entity_id=job.id,
        changes={"kind": job.kind, "project_id": str(project_id) if project_id else None},
    )
    await commit_or_conflict(session, "Job could not be created.")

    assert_transition(job.job_state, JobState.QUEUED)
    job.state = JobState.QUEUED.value
    job.queued_at = _dt.datetime.now(_dt.UTC)
    # Committed *before* dispatch: the worker looks the job up by id, so the row
    # has to be visible to another process by the time the message is sent.
    await commit_or_conflict(session, "Job could not be queued.")

    try:
        task_id = _dispatch(job.id)
    except Exception as exc:
        job.state = JobState.FAILED.value
        job.error = f"Could not be dispatched to the queue: {exc}"
        job.finished_at = _dt.datetime.now(_dt.UTC)
        await commit_or_conflict(session, "Job could not be marked failed.")
        logger.error(
            "job dispatch failed",
            exc_info=exc,
            extra={"event_type": "job.dispatch_failed"},
        )
        raise ServiceUnavailableError(
            "The job queue is unavailable; the job was not started."
        ) from exc

    job.celery_task_id = task_id
    await commit_and_refresh(session, job, "Job could not be updated.")
    logger.info("job queued", extra={"event_type": "job.queued"})
    return job


def _dispatch(job_id: uuid.UUID) -> str:
    """Send the job to the broker and return the broker's task id."""
    from qe_worker.celery_app import celery_app

    return str(celery_app.send_task(RUN_JOB_TASK, args=[str(job_id)]).id)


async def get_job(session: AsyncSession, principal: Principal, job_id: uuid.UUID) -> Job:
    """Load one job from the caller's organisation (the polling read)."""
    principal.require(Permission.JOB_READ)
    stmt = select(Job).where(Job.id == job_id, Job.organisation_id == principal.organisation_id)
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        raise JobNotFoundError("Job not found.")
    return job


async def list_jobs(
    session: AsyncSession,
    principal: Principal,
    *,
    limit: int,
    offset: int,
    state: JobState | None = None,
    project_id: uuid.UUID | None = None,
) -> tuple[list[Job], int]:
    """Return one page of the caller's organisation's jobs, newest first."""
    principal.require(Permission.JOB_READ)
    filters = [Job.organisation_id == principal.organisation_id]
    if state is not None:
        filters.append(Job.state == state.value)
    if project_id is not None:
        filters.append(Job.project_id == project_id)

    total = (
        await session.execute(select(func.count()).select_from(Job).where(*filters))
    ).scalar_one()
    stmt = (
        select(Job)
        .where(*filters)
        .order_by(Job.created_at.desc(), Job.id)
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(stmt)).scalars().all()), total


async def count_jobs_by_state(session: AsyncSession, principal: Principal) -> dict[str, int]:
    """Job counts per state for the caller's organisation (used by System Health)."""
    principal.require(Permission.JOB_READ)
    stmt = (
        select(Job.state, func.count())
        .where(Job.organisation_id == principal.organisation_id)
        .group_by(Job.state)
    )
    counts = {state.value: 0 for state in JobState}
    for state, count in (await session.execute(stmt)).all():
        counts[str(state)] = int(count)
    return counts


__all__ = [
    "RUN_JOB_TASK",
    "count_jobs_by_state",
    "create_job",
    "get_job",
    "list_jobs",
]
