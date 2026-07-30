"""Job routes — the asynchronous request lifecycle.

``POST /jobs`` returns **202 Accepted** with the job record; the client then
polls ``GET /jobs/{id}`` until ``state`` is terminal.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from qe_api.dependencies import SessionDep, require
from qe_api.schemas import JobCreate, JobRead, Page
from qe_api.services import jobs as job_service
from qe_api.services.support import DEFAULT_LIMIT, MAX_LIMIT
from qe_auth import Permission, Principal
from qe_common.jobs import JobState

router = APIRouter(prefix="/jobs", tags=["jobs"])

ReaderDep = Annotated[Principal, Depends(require(Permission.JOB_READ))]
CreatorDep = Annotated[Principal, Depends(require(Permission.JOB_CREATE))]
LimitDep = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
OffsetDep = Annotated[int, Query(ge=0)]


@router.post(
    "",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create and enqueue a job",
)
async def create_job(payload: JobCreate, session: SessionDep, principal: CreatorDep) -> JobRead:
    """Accept the work and hand back the record to poll."""
    job = await job_service.create_job(
        session,
        principal,
        kind=payload.kind,
        payload=payload.payload,
        project_id=payload.project_id,
    )
    return JobRead.model_validate(job)


@router.get("", response_model=Page[JobRead], summary="List jobs, newest first")
async def list_jobs(
    session: SessionDep,
    principal: ReaderDep,
    state: JobState | None = None,
    project_id: uuid.UUID | None = None,
    limit: LimitDep = DEFAULT_LIMIT,
    offset: OffsetDep = 0,
) -> Page[JobRead]:
    jobs, total = await job_service.list_jobs(
        session, principal, limit=limit, offset=offset, state=state, project_id=project_id
    )
    return Page(
        items=[JobRead.model_validate(job) for job in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}", response_model=JobRead, summary="Poll a job's status")
async def get_job(job_id: uuid.UUID, session: SessionDep, principal: ReaderDep) -> JobRead:
    return JobRead.model_validate(await job_service.get_job(session, principal, job_id))


__all__ = ["router"]
