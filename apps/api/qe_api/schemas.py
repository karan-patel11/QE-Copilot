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
from qe_common.test_generation import SourceType, TestFramework
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


# --- Test generation (§16.3, ADR-0212) --------------------------------------


class TestGenerationRequestCreate(BaseModel):
    """Body of ``POST /test-generation/requests``.

    ``configuration`` is validated against :class:`TestGeneratorConfig` in the
    route *before* anything is written, so an option this phase cannot honour
    costs nothing (ADR-0212 Decision 2).
    """

    project_id: uuid.UUID
    title: str = Field(min_length=1, max_length=255)
    source_type: SourceType = SourceType.REQUIREMENT_TEXT
    source_reference: str = Field(min_length=1, description="Requirement text, or a storage key.")
    framework: TestFramework = TestFramework.PYTEST
    repository_id: uuid.UUID | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)


class TestGenerationRequestRead(BaseModel):
    """One generation request, as clients poll it.

    Deliberately does **not** expose ``test_generation_requests.prompt_version``:
    that column holds the detailed-generation version only, and four prompts are
    involved in every run. :attr:`prompt_versions` carries all four
    (ADR-0212 Decision 4).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    repository_id: uuid.UUID | None
    job_id: uuid.UUID | None
    title: str
    source_type: str
    framework: str
    status: JobState
    configuration: dict[str, Any]
    created_at: _dt.datetime
    updated_at: _dt.datetime

    #: Free-text failure reason, and its structured counterpart. A client
    #: branches on the code — ``PROVIDER_*`` is retryable, ``PROMPT_TEMPLATE_DRIFT``
    #: and ``TEST_CONFIG_UNSUPPORTED`` are not (ADR-0212 Decision 5).
    error: str | None = None
    error_code: str | None = None

    #: All four stage prompts. Empty until the pipeline reaches its provider
    #: stages — an empty map says "no stage has run", where a null singular
    #: string could not distinguish that from "not recorded".
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    case_count: int = 0
    produced_by_type: dict[str, int] = Field(default_factory=dict)
    #: Requested case kinds that no generated case carries. **A reported gap, not
    #: an error** — a requirement with no failure conditions legitimately yields
    #: no negative cases (ADR-0208, ADR-0212 Decision 6).
    unmet_requested_kinds: list[str] = Field(default_factory=list)
    coverage_notes: str | None = None
    model_run_ids: list[str] = Field(default_factory=list)
    #: How many cases passed the §22.2 static chain. A failing case is persisted
    #: and shown with its reasons, never dropped (ADR-0205).
    validation_passed: int = 0
    validation_failed: int = 0

    @classmethod
    def from_row(cls, row: Any) -> TestGenerationRequestRead:
        """Build from the ORM row, unpacking the ``summary`` JSONB."""
        summary: dict[str, Any] = row.summary or {}
        validation: dict[str, Any] = summary.get("validation", {})
        return cls(
            id=row.id,
            project_id=row.project_id,
            repository_id=row.repository_id,
            job_id=row.job_id,
            title=row.title,
            source_type=row.source_type,
            framework=row.framework,
            status=JobState(row.status),
            configuration=row.configuration or {},
            created_at=row.created_at,
            updated_at=row.updated_at,
            error=row.error,
            error_code=row.error_code,
            prompt_versions=summary.get("prompt_versions", {}),
            case_count=summary.get("case_count", 0),
            produced_by_type=summary.get("produced_by_type", {}),
            unmet_requested_kinds=summary.get("unmet_requested_kinds", []),
            coverage_notes=summary.get("coverage_notes"),
            model_run_ids=summary.get("model_run_ids", []),
            validation_passed=validation.get("passed", 0),
            validation_failed=validation.get("failed", 0),
        )


class GeneratedTestCaseRead(BaseModel):
    """One generated case — the §11.5 L873-885 display fields."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    request_id: uuid.UUID
    ordinal: int
    title: str
    objective: str
    preconditions: str | None
    test_data: dict[str, Any]
    steps: list[Any]
    expected_result: str
    priority: str
    tags: list[str]
    test_type: str
    framework: str
    generated_code: str
    schema_valid: bool
    syntax_valid: bool
    validation_errors: list[dict[str, Any]]
    #: Stays null in this phase — the sandbox is P1 (ADR-0205). Never implies the
    #: stronger claim that the test passes.
    execution_status: str | None
    human_status: str
    duplicate_of: uuid.UUID | None
    duplicate_score: float | None
    is_edited: bool
    reviewed_by: uuid.UUID | None
    reviewed_at: _dt.datetime | None
    created_at: _dt.datetime

    @property
    def validation_status(self) -> str:
        """The single status §11.5 L883 displays, derived from the two booleans."""
        return "PASSED" if self.schema_valid and self.syntax_valid else "FAILED"


class TestCaseReviewRequest(BaseModel):
    """Optional reviewer note attached to an approve or reject."""

    note: str | None = Field(default=None, max_length=2000)


class TestCaseValidationResponse(BaseModel):
    """Result of re-running the static chain on a stored case."""

    id: uuid.UUID
    schema_valid: bool
    syntax_valid: bool
    validation_status: str
    validation_errors: list[dict[str, Any]]
