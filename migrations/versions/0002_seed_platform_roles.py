"""seed the five platform roles

Revision ID: 0002_roles
Revises: 0001_baseline
Create Date: 2026-07-30

ADR-0104: the design's five roles replace the Phase 0 placeholder names, which
were declared in code but never seeded. Role names are inlined here rather than
imported from ``qe_auth`` so this migration stays a fixed historical snapshot.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_roles"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES: list[tuple[str, str]] = [
    ("engineer", "Writes product code; consumes generated tests and triage output."),
    ("quality_engineer", "Owns test assets for a project; curates repositories and jobs."),
    ("qe_lead", "Leads quality for an organisation; manages projects and reviews audits."),
    ("platform_engineer", "Operates the platform; manages projects, repositories, and health."),
    ("administrator", "Full administrative control, including users and role assignment."),
]


def upgrade() -> None:
    roles = sa.table(
        "roles",
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(roles, [{"name": name, "description": desc} for name, desc in ROLES])


def downgrade() -> None:
    names = ", ".join(f"'{name}'" for name, _ in ROLES)
    # user_roles rows referencing these roles cascade away with them.
    op.execute(f"DELETE FROM roles WHERE name IN ({names})")  # noqa: S608
