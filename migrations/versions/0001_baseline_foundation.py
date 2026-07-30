"""baseline foundation: organisations, users, roles, user_roles, projects, repositories

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-30

Phase 0 baseline. Creates ONLY the six foundation tables plus the pgvector
extension. All later-phase tables (jobs, test suites, defects, knowledge
documents, evaluations, embeddings, ...) are intentionally deferred:
    TODO(phase-1): jobs
    TODO(phase-3): knowledge_documents, embeddings (pgvector columns)
    TODO(phase-4): test_suites, test_cases
    TODO(phase-5): defects, triage_results
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def _timestamps() -> list[sa.Column]:
    """Fresh audit-timestamp columns (a Column instance binds to one table)."""
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    # pgvector extension (ADR-0009). Required now so later-phase embedding
    # columns can be added without a superuser step at that time.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "organisations",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("slug", name="uq_organisations_slug"),
    )

    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_organisation_id", "users", ["organisation_id"])

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_roles"),
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organisation_id", "slug", name="uq_projects_org_slug"),
    )
    op.create_index("ix_projects_organisation_id", "projects", ["organisation_id"])

    op.create_table(
        "repositories",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=64), server_default="github", nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("default_branch", sa.String(length=255), server_default="main", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "url", name="uq_repositories_project_url"),
    )
    op.create_index("ix_repositories_project_id", "repositories", ["project_id"])


def downgrade() -> None:
    op.drop_table("repositories")
    op.drop_table("projects")
    op.drop_table("user_roles")
    op.drop_table("users")
    op.drop_table("roles")
    op.drop_table("organisations")
    # The vector extension is left installed on downgrade; dropping it could
    # affect other schemas sharing the database.
