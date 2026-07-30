"""Audit logging (ADR-0108).

``record_audit`` *stages* a row — it never commits. The caller commits, so the
audited change and its audit row land in one transaction: an action can never be
applied without its record, and a rolled-back action leaves no trace behind.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from qe_auth import Permission, Principal
from qe_common.audit import AuditAction, AuditEntity
from qe_database.models import AuditLog
from qe_observability import current_log_context


def _request_id() -> str | None:
    """Read the correlation id bound by the API middleware, if there is one."""
    value = current_log_context().get("request_id")
    return str(value) if value else None


async def record_audit(
    session: AsyncSession,
    principal: Principal,
    *,
    action: AuditAction,
    entity_type: AuditEntity,
    entity_id: uuid.UUID | None,
    changes: dict[str, Any] | None = None,
) -> AuditLog:
    """Stage an audit row for the caller's action. Does not commit."""
    entry = AuditLog(
        organisation_id=principal.organisation_id,
        actor_user_id=principal.user_id,
        actor_email=principal.email,
        action=action.value,
        entity_type=entity_type.value,
        entity_id=entity_id,
        request_id=_request_id(),
        changes=changes,
    )
    session.add(entry)
    return entry


async def list_audit_logs(
    session: AsyncSession,
    principal: Principal,
    *,
    limit: int,
    offset: int,
    entity_type: AuditEntity | None = None,
    entity_id: uuid.UUID | None = None,
    action: AuditAction | None = None,
) -> tuple[list[AuditLog], int]:
    """Return one page of the caller's organisation's audit trail, newest first."""
    principal.require(Permission.AUDIT_READ)
    filters = [AuditLog.organisation_id == principal.organisation_id]
    if entity_type is not None:
        filters.append(AuditLog.entity_type == entity_type.value)
    if entity_id is not None:
        filters.append(AuditLog.entity_id == entity_id)
    if action is not None:
        filters.append(AuditLog.action == action.value)

    total = (
        await session.execute(select(func.count()).select_from(AuditLog).where(*filters))
    ).scalar_one()
    stmt = (
        select(AuditLog)
        .where(*filters)
        .order_by(AuditLog.created_at.desc(), AuditLog.id)
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(stmt)).scalars().all()), total


__all__ = ["list_audit_logs", "record_audit"]
