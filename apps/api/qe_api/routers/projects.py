"""Project routes — every operation is scoped to the caller's organisation."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from qe_api.dependencies import SessionDep, require
from qe_api.schemas import Page, ProjectCreate, ProjectRead, ProjectUpdate
from qe_api.services import projects as project_service
from qe_api.services.support import DEFAULT_LIMIT, MAX_LIMIT
from qe_auth import Permission, Principal

router = APIRouter(prefix="/projects", tags=["projects"])

ReaderDep = Annotated[Principal, Depends(require(Permission.PROJECT_READ))]
WriterDep = Annotated[Principal, Depends(require(Permission.PROJECT_WRITE))]
LimitDep = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
OffsetDep = Annotated[int, Query(ge=0)]


@router.get("", response_model=Page[ProjectRead], summary="List projects")
async def list_projects(
    session: SessionDep,
    principal: ReaderDep,
    limit: LimitDep = DEFAULT_LIMIT,
    offset: OffsetDep = 0,
) -> Page[ProjectRead]:
    projects, total = await project_service.list_projects(
        session, principal, limit=limit, offset=offset
    )
    return Page(
        items=[ProjectRead.model_validate(p) for p in projects],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "", response_model=ProjectRead, status_code=status.HTTP_201_CREATED, summary="Create a project"
)
async def create_project(
    payload: ProjectCreate, session: SessionDep, principal: WriterDep
) -> ProjectRead:
    project = await project_service.create_project(
        session,
        principal,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
    )
    return ProjectRead.model_validate(project)


@router.get("/{project_id}", response_model=ProjectRead, summary="Fetch a project")
async def get_project(
    project_id: uuid.UUID, session: SessionDep, principal: ReaderDep
) -> ProjectRead:
    return ProjectRead.model_validate(
        await project_service.get_project(session, principal, project_id)
    )


@router.patch("/{project_id}", response_model=ProjectRead, summary="Update a project")
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    session: SessionDep,
    principal: WriterDep,
) -> ProjectRead:
    project = await project_service.update_project(
        session, principal, project_id, name=payload.name, description=payload.description
    )
    return ProjectRead.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a project")
async def delete_project(
    project_id: uuid.UUID, session: SessionDep, principal: WriterDep
) -> Response:
    await project_service.delete_project(session, principal, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
