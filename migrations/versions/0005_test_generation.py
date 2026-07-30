"""test generation: test_generation_requests, generated_test_cases, model_runs

Revision ID: 0005_testgen
Revises: 0004_audit
Create Date: 2026-07-30

ADR-0203. All three tables are rooted at ``organisations`` through ON DELETE
CASCADE, inheriting the Phase 1 tenancy model unchanged.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_testgen"
down_revision: str | None = "0004_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    """Fresh audit-timestamp columns (a Column instance binds to one table)."""
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "test_generation_requests",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        # Untrusted input: treated as data, never as instructions (ADR-0205).
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column("framework", sa.String(length=32), server_default="pytest", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        # The request outlives the user who made it.
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_test_generation_requests_org_created",
        "test_generation_requests",
        ["organisation_id", "created_at"],
    )
    op.create_index(
        "ix_test_generation_requests_project_id", "test_generation_requests", ["project_id"]
    )
    op.create_index("ix_test_generation_requests_job_id", "test_generation_requests", ["job_id"])
    op.create_index("ix_test_generation_requests_status", "test_generation_requests", ["status"])

    op.create_table(
        "generated_test_cases",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        # Denormalised so tenant filtering never needs a join.
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), server_default="0", nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("test_type", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("framework", sa.String(length=32), server_default="pytest", nullable=False),
        # Model output. Never executed anywhere in this phase (ADR-0205).
        sa.Column("code", sa.Text(), nullable=False),
        # Nothing auto-approves.
        sa.Column(
            "status", sa.String(length=32), server_default="PENDING_REVIEW", nullable=False
        ),
        sa.Column(
            "validation_status", sa.String(length=32), server_default="PASSED", nullable=False
        ),
        sa.Column(
            "validation_errors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("duplicate_of", sa.Uuid(), nullable=True),
        sa.Column("duplicate_score", sa.Double(), nullable=True),
        sa.Column("is_edited", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["request_id"], ["test_generation_requests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["duplicate_of"], ["generated_test_cases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_generated_test_cases_request_ordinal",
        "generated_test_cases",
        ["request_id", "ordinal"],
    )
    op.create_index(
        "ix_generated_test_cases_org_created",
        "generated_test_cases",
        ["organisation_id", "created_at"],
    )
    op.create_index("ix_generated_test_cases_status", "generated_test_cases", ["status"])

    op.create_table(
        "model_runs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cache_read_input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "cache_creation_input_tokens", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), server_default="0", nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="SUCCEEDED", nullable=False),
        sa.Column("stop_reason", sa.String(length=32), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        # Retries are visible rather than collapsed into one row.
        sa.Column("attempts", sa.Integer(), server_default="1", nullable=False),
        # Immutable, like audit_logs: no updated_at.
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["request_id"], ["test_generation_requests.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_model_runs_org_created", "model_runs", ["organisation_id", "created_at"])
    op.create_index("ix_model_runs_job_id", "model_runs", ["job_id"])
    op.create_index("ix_model_runs_request_id", "model_runs", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_model_runs_request_id", table_name="model_runs")
    op.drop_index("ix_model_runs_job_id", table_name="model_runs")
    op.drop_index("ix_model_runs_org_created", table_name="model_runs")
    op.drop_table("model_runs")

    op.drop_index("ix_generated_test_cases_status", table_name="generated_test_cases")
    op.drop_index("ix_generated_test_cases_org_created", table_name="generated_test_cases")
    op.drop_index("ix_generated_test_cases_request_ordinal", table_name="generated_test_cases")
    op.drop_table("generated_test_cases")

    op.drop_index("ix_test_generation_requests_status", table_name="test_generation_requests")
    op.drop_index("ix_test_generation_requests_job_id", table_name="test_generation_requests")
    op.drop_index("ix_test_generation_requests_project_id", table_name="test_generation_requests")
    op.drop_index("ix_test_generation_requests_org_created", table_name="test_generation_requests")
    op.drop_table("test_generation_requests")
