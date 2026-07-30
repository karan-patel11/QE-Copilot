"""Project services — CRUD scoped to the caller's organisation."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from qe_api.services.audit import record_audit
from qe_api.services.support import (
    commit_and_refresh,
    commit_or_conflict,
    flush_or_conflict,
    slugify,
)
from qe_auth import Permission, Principal
from qe_common.audit import AuditAction, AuditEntity
from qe_common.errors import NotFoundError
from qe_database.models import Project


async def list_projects(
    session: AsyncSession, principal: Principal, *, limit: int, offset: int
) -> tuple[list[Project], int]:
    """Return one page of the caller's organisation's projects, plus the total."""
    principal.require(Permission.PROJECT_READ)
    scope = Project.organisation_id == principal.organisation_id
    total = (
        await session.execute(select(func.count()).select_from(Project).where(scope))
    ).scalar_one()
    stmt = (
        select(Project).where(scope).order_by(Project.name, Project.id).limit(limit).offset(offset)
    )
    return list((await session.execute(stmt)).scalars().all()), total


async def get_project(
    session: AsyncSession, principal: Principal, project_id: uuid.UUID
) -> Project:
    """Load one project. A project in another tenant reads as not found."""
    principal.require(Permission.PROJECT_READ)
    stmt = select(Project).where(
        Project.id == project_id,
        Project.organisation_id == principal.organisation_id,
    )
    project = (await session.execute(stmt)).scalar_one_or_none()
    if project is None:
        raise NotFoundError("Project not found.")
    return project


async def create_project(
    session: AsyncSession,
    principal: Principal,
    *,
    name: str,
    slug: str | None = None,
    description: str | None = None,
) -> Project:
    """Create a project inside the caller's organisation."""
    principal.require(Permission.PROJECT_WRITE)
    project = Project(
        organisation_id=principal.organisation_id,
        name=name,
        slug=slugify(slug or name),
        description=description,
    )
    session.add(project)
    await flush_or_conflict(session, "A project with that slug already exists.")
    await record_audit(
        session,
        principal,
        action=AuditAction.CREATE,
        entity_type=AuditEntity.PROJECT,
        entity_id=project.id,
        changes={"name": project.name, "slug": project.slug},
    )
    await commit_or_conflict(session, "A project with that slug already exists.")
    return project


async def update_project(
    session: AsyncSession,
    principal: Principal,
    project_id: uuid.UUID,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Project:
    """Update mutable project attributes. The slug is immutable."""
    principal.require(Permission.PROJECT_WRITE)
    project = await get_project(session, principal, project_id)
    changes: dict[str, object] = {}
    if name is not None:
        changes["name"] = {"from": project.name, "to": name}
        project.name = name
    if description is not None:
        changes["description"] = {"from": project.description, "to": description}
        project.description = description

    await flush_or_conflict(session, "Project could not be updated.")
    await record_audit(
        session,
        principal,
        action=AuditAction.UPDATE,
        entity_type=AuditEntity.PROJECT,
        entity_id=project.id,
        changes=changes,
    )
    return await commit_and_refresh(session, project, "Project could not be updated.")


async def delete_project(
    session: AsyncSession, principal: Principal, project_id: uuid.UUID
) -> Project:
    """Delete a project and everything beneath it. Returns the deleted row."""
    principal.require(Permission.PROJECT_WRITE)
    project = await get_project(session, principal, project_id)
    snapshot = {"name": project.name, "slug": project.slug}
    await session.delete(project)
    await flush_or_conflict(session, "Project could not be deleted.")
    await record_audit(
        session,
        principal,
        action=AuditAction.DELETE,
        entity_type=AuditEntity.PROJECT,
        entity_id=project.id,
        changes=snapshot,
    )
    await commit_or_conflict(session, "Project could not be deleted.")
    return project


__all__ = [
    "create_project",
    "delete_project",
    "get_project",
    "list_projects",
    "update_project",
]
