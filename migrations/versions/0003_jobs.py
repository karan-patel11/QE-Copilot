"""jobs table — persisted asynchronous work records

Revision ID: 0003_jobs
Revises: 0002_roles
Create Date: 2026-07-30

ADR-0107: the row is the authoritative job state, written by the API on creation
and by the worker on every subsequent transition.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_jobs"
down_revision: str | None = "0002_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("celery_task_id", sa.String(length=155), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        # The job record outlives the user who created it.
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_jobs_organisation_id_created_at", "jobs", ["organisation_id", "created_at"]
    )
    op.create_index("ix_jobs_state", "jobs", ["state"])
    op.create_index("ix_jobs_project_id", "jobs", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_project_id", table_name="jobs")
    op.drop_index("ix_jobs_state", table_name="jobs")
    op.drop_index("ix_jobs_organisation_id_created_at", table_name="jobs")
    op.drop_table("jobs")
