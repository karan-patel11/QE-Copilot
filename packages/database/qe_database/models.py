"""ORM models.

Phase 0 established tenancy, identity, RBAC, and project/repository
registration. Phase 1 adds the tables the core platform runs on: ``jobs`` (the
asynchronous work record) and ``audit_logs``. Feature tables (test_suites,
defects, knowledge_documents, evaluations, embeddings, ...) remain deferred and
are tracked as ``TODO(phase-N)`` in the design.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from qe_common.jobs import JobState
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


__all__ = [
    "Job",
    "Organisation",
    "Project",
    "Repository",
    "Role",
    "User",
    "UserRole",
]
