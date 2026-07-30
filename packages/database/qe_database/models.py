"""ORM models.

Phase 0 established tenancy, identity, RBAC, and project/repository
registration. Phase 1 added the core-platform tables: ``jobs`` (the asynchronous
work record) and ``audit_logs``. Phase 2 adds test generation:
``test_generation_requests``, ``generated_test_cases``, and ``model_runs``
(ADR-0203). Later-phase tables (defects, knowledge_documents, evaluations,
embeddings, ...) remain deferred and are tracked as ``TODO(phase-N)``.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from qe_common.jobs import JobState
from qe_common.test_generation import (
    ModelRunStatus,
    TestCaseStatus,
    TestFramework,
    ValidationStatus,
)
from qe_database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Organisation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tenant. Design-doc spelling ``organisations`` is preserved (ADR-0012)."""

    __tablename__ = "organisations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    # ``passive_deletes`` defers to the database's ON DELETE CASCADE instead of
    # having the ORM load children and NULL out their (NOT NULL) foreign key.
    users: Mapped[list[User]] = relationship(
        back_populates="organisation", cascade="all, delete", passive_deletes=True
    )
    projects: Mapped[list[Project]] = relationship(
        back_populates="organisation", cascade="all, delete", passive_deletes=True
    )


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    organisation: Mapped[Organisation] = relationship(back_populates="users")
    roles: Mapped[list[Role]] = relationship(secondary="user_roles", back_populates="users")


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)

    users: Mapped[list[User]] = relationship(secondary="user_roles", back_populates="roles")


class UserRole(Base):
    """Association table joining users and roles (many-to-many RBAC)."""

    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    organisation: Mapped[Organisation] = relationship(back_populates="projects")
    repositories: Mapped[list[Repository]] = relationship(
        back_populates="project", cascade="all, delete", passive_deletes=True
    )

    __table_args__ = (UniqueConstraint("organisation_id", "slug", name="uq_projects_org_slug"),)


class Repository(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "repositories"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="github")
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")

    project: Mapped[Project] = relationship(back_populates="repositories")

    __table_args__ = (UniqueConstraint("project_id", "url", name="uq_repositories_project_url"),)


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An asynchronous unit of work.

    The row is the authoritative record of a job's state: the API writes
    ``PENDING`` then ``QUEUED``, and the worker owns every transition after
    that, so polling this table always reflects reality rather than what the
    broker last reported (ADR-0107).
    """

    __tablename__ = "jobs"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    # Kept when the user is deleted: an audit trail must outlive its actor.
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default=JobState.PENDING.value)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    celery_task_id: Mapped[str | None] = mapped_column(String(155))
    queued_at: Mapped[_dt.datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[_dt.datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[_dt.datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_jobs_organisation_id_created_at", "organisation_id", "created_at"),
        Index("ix_jobs_state", "state"),
        Index("ix_jobs_project_id", "project_id"),
    )

    @property
    def job_state(self) -> JobState:
        """The ``state`` column as its enum value."""
        return JobState(self.state)


class AuditLog(UUIDPrimaryKeyMixin, Base):
    """An immutable record of one mutating action (ADR-0108).

    No ``updated_at``: an audit row is never modified. The actor's email is
    denormalised alongside the foreign key so the record still names who acted
    after that user is deleted.
    """

    __tablename__ = "audit_logs"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_email: Mapped[str | None] = mapped_column(String(320))

    action: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # Deliberately not a foreign key: the row must outlive the entity it describes.
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    request_id: Mapped[str | None] = mapped_column(String(64))
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_audit_logs_organisation_id_created_at", "organisation_id", "created_at"),
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
    )


class TestGenerationRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One test-generation request — the unit the API creates and clients poll.

    Executed by a Phase 1 job (ADR-0204); ``status`` mirrors
    :class:`qe_common.jobs.JobState` so there is one lifecycle vocabulary rather
    than two, and the row stays self-describing for polling.
    """

    __tablename__ = "test_generation_requests"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="SET NULL")
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    # The request outlives the user who made it.
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Untrusted input. Treated as data, never as instructions (ADR-0205, N9).
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    framework: Mapped[str] = mapped_column(
        String(32), nullable=False, default=TestFramework.PYTEST.value
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=JobState.PENDING.value)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    test_cases: Mapped[list[GeneratedTestCase]] = relationship(
        back_populates="request", cascade="all, delete", passive_deletes=True
    )

    __table_args__ = (
        Index(
            "ix_test_generation_requests_org_created",
            "organisation_id",
            "created_at",
        ),
        Index("ix_test_generation_requests_project_id", "project_id"),
        Index("ix_test_generation_requests_job_id", "job_id"),
        Index("ix_test_generation_requests_status", "status"),
    )

    @property
    def job_state(self) -> JobState:
        """The ``status`` column as its enum value."""
        return JobState(self.status)


class GeneratedTestCase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One generated test case — the reviewable unit.

    ``code`` is model output and is **never executed** anywhere in this phase
    (ADR-0205). ``validation_status`` reports the static chain only.
    """

    __tablename__ = "generated_test_cases"

    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_generation_requests.id", ondelete="CASCADE"), nullable=False
    )
    # Denormalised so tenant filtering never needs a join.
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )

    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    test_type: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    framework: Mapped[str] = mapped_column(
        String(32), nullable=False, default=TestFramework.PYTEST.value
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=TestCaseStatus.PENDING_REVIEW.value
    )
    validation_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ValidationStatus.PASSED.value
    )
    validation_errors: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )

    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("generated_test_cases.id", ondelete="SET NULL")
    )
    duplicate_score: Mapped[float | None] = mapped_column(Double)

    is_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[_dt.datetime | None] = mapped_column(DateTime(timezone=True))

    request: Mapped[TestGenerationRequest] = relationship(back_populates="test_cases")

    __table_args__ = (
        Index("ix_generated_test_cases_request_ordinal", "request_id", "ordinal"),
        Index("ix_generated_test_cases_org_created", "organisation_id", "created_at"),
        Index("ix_generated_test_cases_status", "status"),
    )


class ModelRun(UUIDPrimaryKeyMixin, Base):
    """One provider call — including failures and refusals (ADR-0201/0203).

    Immutable, like :class:`AuditLog`: no ``updated_at``. Carries metering and
    provenance only — **no prompt or response text** — so a requirement holding
    sensitive data is not duplicated into a second table.
    """

    __tablename__ = "model_runs"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("test_generation_requests.id", ondelete="CASCADE")
    )

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(64))

    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_read_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_creation_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[decimal.Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=decimal.Decimal("0")
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ModelRunStatus.SUCCEEDED.value
    )
    stop_reason: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(64))
    #: Retries are visible rather than collapsed into one row.
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_model_runs_org_created", "organisation_id", "created_at"),
        Index("ix_model_runs_job_id", "job_id"),
        Index("ix_model_runs_request_id", "request_id"),
    )


__all__ = [
    "AuditLog",
    "GeneratedTestCase",
    "Job",
    "ModelRun",
    "Organisation",
    "Project",
    "Repository",
    "Role",
    "TestGenerationRequest",
    "User",
    "UserRole",
]
