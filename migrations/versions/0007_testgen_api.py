"""testgen api: idempotency key and structured error code on generation requests

Revision ID: 0007_testgen_api
Revises: 0006_ai_gov
Create Date: 2026-07-31

ADR-0212. Two columns on the **existing** ``test_generation_requests`` table and
one partial unique index. No new tables, and nothing else is touched.

``idempotency_key`` (§26.8 L2190) — no idempotency mechanism existed anywhere in
the codebase before this. Without one, a client retrying a POST creates a second
full generation: four more billed provider calls for one logical request.

``error_code`` (ADR-0212 Decision 5) — template drift is raised inside the worker
and so never becomes an HTTP status; it becomes a failed request row. A structured
code lets the frontend distinguish "retry might work" from "this needs an
engineer" without pattern-matching a free-text message.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_testgen_api"
down_revision: str | None = "0006_ai_gov"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "test_generation_requests"
_IDEMPOTENCY_INDEX = "uq_test_generation_requests_idempotency"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    op.add_column(_TABLE, sa.Column("error_code", sa.String(length=64), nullable=True))

    # Partial, so the many rows without a key do not collide with each other.
    # Scoped per organisation because a key is only ever unique to the client
    # that issued it — two tenants may legitimately send the same string.
    op.create_index(
        _IDEMPOTENCY_INDEX,
        _TABLE,
        ["organisation_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(_IDEMPOTENCY_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, "error_code")
    op.drop_column(_TABLE, "idempotency_key")
