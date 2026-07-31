"""ai governance: prompt_versions (+ one index on the existing model_runs)

Revision ID: 0006_ai_gov
Revises: 0005_testgen
Create Date: 2026-07-31

ADR-0209. This migration creates exactly ONE table.

``model_runs`` already exists from 0005 (ADR-0203, N2 gate PASS) with all twelve
§15.8 columns; it is NOT recreated or altered here. The only thing 0006 does to
it is add the index on ``prompt_version_id`` that 0005 omitted.

``model_runs.prompt_version_id`` stays ``String(64)`` holding
``prompt_versions.version`` and is deliberately **not** a foreign key. See
ADR-0203's hazard note and ADR-0209 Decision 2 for the backfill this defers.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from qe_common.prompts import PROMPT_STATUS_ORDER

revision: str = "0006_ai_gov"
down_revision: str | None = "0005_testgen"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Generated from the same tuple the ORM and the service layer use, so the
# database vocabulary cannot drift from PromptStatus (ADR-0209 Decision 3).
_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in PROMPT_STATUS_ORDER)


def upgrade() -> None:
    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("prompt_name", sa.String(length=64), nullable=False),
        # The exact string model_runs.prompt_version_id holds, e.g. "testgen-v3".
        sa.Column("version", sa.String(length=64), nullable=False),
        # Mirror of the git-versioned source template (ADR-0202, §19 L1772).
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="DRAFT", nullable=False),
        # The version outlives the user who registered it.
        sa.Column("created_by", sa.Uuid(), nullable=True),
        # SHA-256 of the source template: makes the mirror claim checkable.
        sa.Column("template_checksum", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        # The DB owns the *set* of legal values; the service owns the *ordering*
        # between them, which a CHECK structurally cannot see (ADR-0209 §3).
        sa.CheckConstraint(f"status IN ({_STATUS_VALUES})", name="ck_prompt_versions_status"),
        # No organisation_id: prompts are platform assets, not tenant data.
    )
    op.create_unique_constraint(
        "uq_prompt_versions_name_version", "prompt_versions", ["prompt_name", "version"]
    )
    # At most one ACTIVE version per prompt, enforced by the database. This is
    # what makes get_active() single-valued under concurrent activation.
    op.create_index(
        "uq_prompt_versions_one_active",
        "prompt_versions",
        ["prompt_name"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "ix_prompt_versions_name_status", "prompt_versions", ["prompt_name", "status"]
    )

    # --- Existing table (0005). Index only; no column is added or altered. ---
    op.create_index("ix_model_runs_prompt_version_id", "model_runs", ["prompt_version_id"])


def downgrade() -> None:
    # model_runs itself belongs to 0005 and must survive this downgrade with its
    # data intact — only the index this migration added comes off.
    op.drop_index("ix_model_runs_prompt_version_id", table_name="model_runs")

    op.drop_index("ix_prompt_versions_name_status", table_name="prompt_versions")
    op.drop_index("uq_prompt_versions_one_active", table_name="prompt_versions")
    op.drop_constraint("uq_prompt_versions_name_version", "prompt_versions", type_="unique")
    op.drop_table("prompt_versions")
