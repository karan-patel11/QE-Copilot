"""Repository services.

Repositories hang off projects, so tenancy is enforced one level up: every
lookup joins ``projects`` and filters on the caller's ``organisation_id``. That
also makes the foreign key unforgeable from the API — a repository can only ever
be attached to a project the caller can already see.
"""

from __future__ import annotations

import uuid

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
from qe_common.errors import NotFoundError
from qe_database.models import Project, Repository

# Providers a repository may be registered against. Anything beyond git hosting
# (artifact registries, ticket trackers) is out of scope for Phase 1.
SUPPORTED_PROVIDERS: frozenset[str] = frozenset({"github", "gitlab", "bitbucket", "azure_devops"})


async def list_repositories(
    session: AsyncSession,
    principal: Principal,
    project_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
) -> tuple[list[Repository], int]:
    """Return one page of a project's repositories, plus the total."""
    principal.require(Permission.REPOSITORY_READ)
    # 404s when the project belongs to another tenant, before any repo is read.
    await get_project(session, principal, project_id)

    scope = Repository.project_id == project_id
    total = (
        await session.execute(select(func.count()).select_from(Repository).where(scope))
    ).scalar_one()
    stmt = (
        select(Repository)
        .where(scope)
        .order_by(Repository.name, Repository.id)
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(stmt)).scalars().all()), total


async def get_repository(
    session: AsyncSession, principal: Principal, repository_id: uuid.UUID
) -> Repository:
    """Load one repository from the caller's organisation."""
    principal.require(Permission.REPOSITORY_READ)
    stmt = (
        select(Repository)
        .join(Project, Project.id == Repository.project_id)
        .where(
            Repository.id == repository_id,
            Project.organisation_id == principal.organisation_id,
        )
    )
    repository = (await session.execute(stmt)).scalar_one_or_none()
    if repository is None:
        raise NotFoundError("Repository not found.")
    return repository


async def create_repository(
    session: AsyncSession,
    principal: Principal,
    project_id: uuid.UUID,
    *,
    name: str,
    url: str,
    provider: str = "github",
    default_branch: str = "main",
) -> Repository:
    """Register a repository under a project the caller can see."""
    principal.require(Permission.REPOSITORY_WRITE)
    await get_project(session, principal, project_id)

    repository = Repository(
        project_id=project_id,
        name=name,
        url=url,
        provider=provider,
        default_branch=default_branch,
    )
    session.add(repository)
    await flush_or_conflict(session, "That repository URL is already registered on this project.")
    await record_audit(
        session,
        principal,
        action=AuditAction.CREATE,
        entity_type=AuditEntity.REPOSITORY,
        entity_id=repository.id,
        changes={"project_id": str(project_id), "name": name, "url": url, "provider": provider},
    )
    await commit_or_conflict(session, "That repository URL is already registered on this project.")
    return repository


async def update_repository(
    session: AsyncSession,
    principal: Principal,
    repository_id: uuid.UUID,
    *,
    name: str | None = None,
    url: str | None = None,
    provider: str | None = None,
    default_branch: str | None = None,
) -> Repository:
    """Update mutable repository attributes."""
    principal.require(Permission.REPOSITORY_WRITE)
    repository = await get_repository(session, principal, repository_id)
    changes: dict[str, object] = {}
    for field, value in (
        ("name", name),
        ("url", url),
        ("provider", provider),
        ("default_branch", default_branch),
    ):
        if value is not None:
            changes[field] = {"from": getattr(repository, field), "to": value}
            setattr(repository, field, value)

    await flush_or_conflict(session, "That repository URL is already registered on this project.")
    await record_audit(
        session,
        principal,
        action=AuditAction.UPDATE,
        entity_type=AuditEntity.REPOSITORY,
        entity_id=repository.id,
        changes=changes,
    )
    return await commit_and_refresh(
        session, repository, "That repository URL is already registered on this project."
    )


async def delete_repository(
    session: AsyncSession, principal: Principal, repository_id: uuid.UUID
) -> Repository:
    """Delete a repository. Returns the deleted row so callers can audit it."""
    principal.require(Permission.REPOSITORY_WRITE)
    repository = await get_repository(session, principal, repository_id)
    snapshot = {"name": repository.name, "url": repository.url}
    await session.delete(repository)
    await flush_or_conflict(session, "Repository could not be deleted.")
    await record_audit(
        session,
        principal,
        action=AuditAction.DELETE,
        entity_type=AuditEntity.REPOSITORY,
        entity_id=repository.id,
        changes=snapshot,
    )
    await commit_or_conflict(session, "Repository could not be deleted.")
    return repository


__all__ = [
    "SUPPORTED_PROVIDERS",
    "create_repository",
    "delete_repository",
    "get_repository",
    "list_repositories",
    "update_repository",
]
