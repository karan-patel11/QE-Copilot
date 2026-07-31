"""test generation: test_generation_requests, generated_test_cases, model_runs

Revision ID: 0005_testgen
Revises: 0004_audit
Create Date: 2026-07-30

ADR-0203. All three tables are rooted at ``organisations`` through ON DELETE
CASCADE, inheriting the Phase 1 tenancy model unchanged.

Amended in place (N2 re-gate) to carry the §15.6 / §15.8 column names verbatim.
The pre-amendment revision renamed and collapsed spec columns — most seriously
folding ``objective / preconditions / test_data / steps / expected_result /
tags`` into one ``description``, which §11.5 L873-885 requires displayed
individually. This revision has only ever existed on this branch and has no
external consumers, so it is amended rather than corrected by a stacked 0006.
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
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        # Untrusted input: treated as data, never as instructions (ADR-0205).
        # Holds the requirement text itself for text-ish source types, and a
        # storage key for uploaded sources (§11.5 L853 input list).
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("framework", sa.String(length=32), server_default="pytest", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column(
            "configuration",
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
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
        # §15.6 L1476-1482: the reviewable body of the case, one column per
        # field, because §11.5 L873-885 displays each of them individually.
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("preconditions", sa.Text(), nullable=True),
        sa.Column(
            "test_data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "steps",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("expected_result", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("test_type", sa.String(length=32), nullable=False),
        sa.Column("framework", sa.String(length=32), server_default="pytest", nullable=False),
        # Model output. Never executed anywhere in this phase (ADR-0205).
        sa.Column("generated_code", sa.Text(), nullable=False),
        # §15.6 L1484-1485: two independent checks, not one collapsed status.
        sa.Column("schema_valid", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("syntax_valid", sa.Boolean(), server_default=sa.false(), nullable=False),
        # Carries *why* a check failed, which the two booleans cannot.
        sa.Column(
            "validation_errors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        # Specified (§15.6 L1487) and displayed (§11.5 L885), but stays NULL in
        # Phase 2: the sandbox that would populate it is P1 (ADR-0205). NULL is
        # the honest "not executed", and P1 then needs no migration.
        sa.Column("execution_status", sa.String(length=32), nullable=True),
        # Nothing auto-approves (§8.2 human-in-the-loop, §11.5 L890).
        sa.Column(
            "human_status", sa.String(length=32), server_default="PENDING_REVIEW", nullable=False
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
    op.create_index(
        "ix_generated_test_cases_human_status", "generated_test_cases", ["human_status"]
    )

    op.create_table(
        "model_runs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        # §15.8 L1542 specifies this as a reference to ``prompt_versions``. That
        # table is deferred (ADR-0202), so in Phase 2 the column holds the
        # version *string*, not a UUID, and is not yet a foreign key. See the
        # hazard note in ADR-0203 before writing this field.
        sa.Column("prompt_version_id", sa.String(length=64), nullable=True),
        sa.Column("input_token_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_token_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cache_read_input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cache_creation_input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "estimated_cost", sa.Numeric(precision=12, scale=6), server_default="0", nullable=False
        ),
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

    op.drop_index("ix_generated_test_cases_human_status", table_name="generated_test_cases")
    op.drop_index("ix_generated_test_cases_org_created", table_name="generated_test_cases")
    op.drop_index("ix_generated_test_cases_request_ordinal", table_name="generated_test_cases")
    op.drop_table("generated_test_cases")

    op.drop_index("ix_test_generation_requests_status", table_name="test_generation_requests")
    op.drop_index("ix_test_generation_requests_job_id", table_name="test_generation_requests")
    op.drop_index("ix_test_generation_requests_project_id", table_name="test_generation_requests")
    op.drop_index("ix_test_generation_requests_org_created", table_name="test_generation_requests")
    op.drop_table("test_generation_requests")
