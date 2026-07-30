"""audit_logs table — immutable record of mutating actions

Revision ID: 0004_audit
Revises: 0003_jobs
Create Date: 2026-07-30

ADR-0108: written in the same transaction as the action it describes, so an
audited change and its audit row commit or roll back together.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_audit"
down_revision: str | None = "0003_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        # Denormalised so the row still names the actor after the user is deleted.
        sa.Column("actor_email", sa.String(length=320), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        # Intentionally not a foreign key: audit rows outlive their entities.
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_audit_logs_organisation_id_created_at", "audit_logs", ["organisation_id", "created_at"]
    )
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_entity", table_name="audit_logs")
    op.drop_index("ix_audit_logs_organisation_id_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")
