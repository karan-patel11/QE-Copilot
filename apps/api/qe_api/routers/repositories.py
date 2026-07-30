"""Repository routes.

Collection routes are nested under a project (that is where a repository comes
from); item routes are flat, since a repository id already identifies its
project.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from qe_api.dependencies import SessionDep, require
from qe_api.schemas import Page, RepositoryCreate, RepositoryRead, RepositoryUpdate
from qe_api.services import repositories as repository_service
from qe_api.services.support import DEFAULT_LIMIT, MAX_LIMIT
from qe_auth import Permission, Principal

project_router = APIRouter(prefix="/projects/{project_id}/repositories", tags=["repositories"])
router = APIRouter(prefix="/repositories", tags=["repositories"])

ReaderDep = Annotated[Principal, Depends(require(Permission.REPOSITORY_READ))]
WriterDep = Annotated[Principal, Depends(require(Permission.REPOSITORY_WRITE))]
LimitDep = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
OffsetDep = Annotated[int, Query(ge=0)]


@project_router.get(
    "", response_model=Page[RepositoryRead], summary="List a project's repositories"
)
async def list_repositories(
    project_id: uuid.UUID,
    session: SessionDep,
    principal: ReaderDep,
    limit: LimitDep = DEFAULT_LIMIT,
    offset: OffsetDep = 0,
) -> Page[RepositoryRead]:
    repositories, total = await repository_service.list_repositories(
        session, principal, project_id, limit=limit, offset=offset
    )
    return Page(
        items=[RepositoryRead.model_validate(r) for r in repositories],
        total=total,
        limit=limit,
        offset=offset,
    )


@project_router.post(
    "",
    response_model=RepositoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a repository on a project",
)
async def create_repository(
    project_id: uuid.UUID,
    payload: RepositoryCreate,
    session: SessionDep,
    principal: WriterDep,
) -> RepositoryRead:
    repository = await repository_service.create_repository(
        session,
        principal,
        project_id,
        name=payload.name,
        url=payload.url,
        provider=payload.provider,
        default_branch=payload.default_branch,
    )
    return RepositoryRead.model_validate(repository)


@router.get("/{repository_id}", response_model=RepositoryRead, summary="Fetch a repository")
async def get_repository(
    repository_id: uuid.UUID, session: SessionDep, principal: ReaderDep
) -> RepositoryRead:
    return RepositoryRead.model_validate(
        await repository_service.get_repository(session, principal, repository_id)
    )


@router.patch("/{repository_id}", response_model=RepositoryRead, summary="Update a repository")
async def update_repository(
    repository_id: uuid.UUID,
    payload: RepositoryUpdate,
    session: SessionDep,
    principal: WriterDep,
) -> RepositoryRead:
    repository = await repository_service.update_repository(
        session,
        principal,
        repository_id,
        name=payload.name,
        url=payload.url,
        provider=payload.provider,
        default_branch=payload.default_branch,
    )
    return RepositoryRead.model_validate(repository)


@router.delete(
    "/{repository_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a repository"
)
async def delete_repository(
    repository_id: uuid.UUID, session: SessionDep, principal: WriterDep
) -> Response:
    await repository_service.delete_repository(session, principal, repository_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["project_router", "router"]
