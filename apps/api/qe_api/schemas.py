"""Request/response models for the v1 API.

Kept in one module so the wire contract for Phase 1 can be read end-to-end.
ORM objects are never returned directly; every response goes through a model
here, which is what keeps internal columns out of the API surface.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from qe_auth import Permission, Role, parse_role
from qe_common.audit import AuditAction, AuditEntity
from qe_common.health import HealthStatus
from qe_common.jobs import JobKind, JobState, is_terminal
from qe_database.models import User

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """One page of a collection, plus the unfiltered total."""

    items: list[T]
    total: int = Field(description="Total rows matching the query, ignoring paging.")
    limit: int
    offset: int


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #


class DevLoginRequest(BaseModel):
    """Dev-mode identity provider credential (ADR-0101): an email address."""

    email: EmailStr = Field(description="Address to sign in as.")


class UserRead(BaseModel):
    """A user as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organisation_id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    roles: list[Role] = Field(default_factory=list)
    created_at: _dt.datetime
    updated_at: _dt.datetime

    @classmethod
    def from_user(cls, user: User) -> UserRead:
        """Serialise a ``User`` whose ``roles`` relationship is already loaded."""
        roles = sorted(
            {role for role in (parse_role(row.name) for row in user.roles) if role is not None}
        )
        return cls(
            id=user.id,
            organisation_id=user.organisation_id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            roles=roles,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


class TokenResponse(BaseModel):
    """OAuth-2-shaped bearer-token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Token lifetime in seconds.")
    user: UserRead


class MeResponse(BaseModel):
    """The caller's identity plus its effective authorisation."""

    user: UserRead
    roles: list[Role]
    permissions: list[Permission]


# --------------------------------------------------------------------------- #
# Users & roles
# --------------------------------------------------------------------------- #


class UserCreate(BaseModel):
    """New user in the caller's organisation."""

    email: EmailStr
    full_name: str | None = Field(default=None, max_length=255)
    roles: list[Role] = Field(
        default_factory=list, description="Requires the role:assign permission."
    )


class UserUpdate(BaseModel):
    """Mutable user attributes; omitted fields are left unchanged."""

    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class RoleAssignment(BaseModel):
    """The complete replacement role set for a user."""

    roles: list[Role]


class RoleRead(BaseModel):
    """An assignable role."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None


# --------------------------------------------------------------------------- #
# Organisations & projects
# --------------------------------------------------------------------------- #


class OrganisationRead(BaseModel):
    """A tenant."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_at: _dt.datetime
    updated_at: _dt.datetime


class OrganisationUpdate(BaseModel):
    """Mutable organisation attributes. The slug is an identifier and immutable."""

    name: str | None = Field(default=None, min_length=1, max_length=255)


class ProjectRead(BaseModel):
    """A project."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organisation_id: uuid.UUID
    name: str
    slug: str
    description: str | None
    created_at: _dt.datetime
    updated_at: _dt.datetime


class ProjectCreate(BaseModel):
    """New project in the caller's organisation."""

    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(
        default=None, max_length=255, description="Derived from name if unset."
    )
    description: str | None = None


class ProjectUpdate(BaseModel):
    """Mutable project attributes; omitted fields are left unchanged."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


# --------------------------------------------------------------------------- #
# Repositories
# --------------------------------------------------------------------------- #

RepositoryProvider = Literal["github", "gitlab", "bitbucket", "azure_devops"]


class RepositoryRead(BaseModel):
    """A registered source repository."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    provider: str
    url: str
    default_branch: str
    created_at: _dt.datetime
    updated_at: _dt.datetime


class RepositoryCreate(BaseModel):
    """Register a repository under a project."""

    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=1024)
    provider: RepositoryProvider = "github"
    default_branch: str = Field(default="main", min_length=1, max_length=255)


class RepositoryUpdate(BaseModel):
    """Mutable repository attributes; omitted fields are left unchanged."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = Field(default=None, min_length=1, max_length=1024)
    provider: RepositoryProvider | None = None
    default_branch: str | None = Field(default=None, min_length=1, max_length=255)


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #


class JobRead(BaseModel):
    """A job record — this is what the polling endpoint returns."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organisation_id: uuid.UUID
    project_id: uuid.UUID | None
    created_by: uuid.UUID | None
    kind: str
    state: JobState
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    attempts: int
    queued_at: _dt.datetime | None
    started_at: _dt.datetime | None
    finished_at: _dt.datetime | None
    created_at: _dt.datetime
    updated_at: _dt.datetime

    @property
    def is_terminal(self) -> bool:
        """Whether the job has reached a final state and will not change again."""
        return is_terminal(self.state)


class JobCreate(BaseModel):
    """Request a unit of asynchronous work."""

    kind: JobKind = Field(description="The kind of work to run.")
    project_id: uuid.UUID | None = Field(
        default=None, description="Optional project the job belongs to."
    )
    payload: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Audit log
# --------------------------------------------------------------------------- #


class AuditLogRead(BaseModel):
    """One immutable audit record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organisation_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_email: str | None
    action: AuditAction
    entity_type: AuditEntity
    entity_id: uuid.UUID | None
    request_id: str | None
    changes: dict[str, Any] | None
    created_at: _dt.datetime


# --------------------------------------------------------------------------- #
# System health
# --------------------------------------------------------------------------- #


class ComponentHealth(BaseModel):
    """Live status of one runtime component."""

    status: HealthStatus
    detail: str | None = Field(default=None, description="Why, when not healthy.")
    metrics: dict[str, Any] = Field(
        default_factory=dict, description="Component-specific measurements."
    )


class SystemHealthResponse(BaseModel):
    """The System Health page's payload — measured per request, never cached."""

    status: HealthStatus = Field(description="Worst component status.")
    checked_at: _dt.datetime
    components: dict[str, ComponentHealth]
    jobs: dict[str, int] = Field(
        default_factory=dict, description="Job counts by state for the caller's organisation."
    )


__all__ = [
    "AuditLogRead",
    "ComponentHealth",
    "DevLoginRequest",
    "JobCreate",
    "JobRead",
    "MeResponse",
    "OrganisationRead",
    "OrganisationUpdate",
    "Page",
    "ProjectCreate",
    "ProjectRead",
    "ProjectUpdate",
    "RepositoryCreate",
    "RepositoryRead",
    "RepositoryUpdate",
    "RoleAssignment",
    "RoleRead",
    "SystemHealthResponse",
    "TokenResponse",
    "UserCreate",
    "UserRead",
    "UserUpdate",
]
