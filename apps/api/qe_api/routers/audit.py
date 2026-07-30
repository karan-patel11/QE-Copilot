"""Audit-trail routes (read-only — audit records are never edited or deleted)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from qe_api.dependencies import SessionDep, require
from qe_api.schemas import AuditLogRead, Page
from qe_api.services import audit as audit_service
from qe_api.services.support import DEFAULT_LIMIT, MAX_LIMIT
from qe_auth import Permission, Principal
from qe_common.audit import AuditAction, AuditEntity

router = APIRouter(prefix="/audit-logs", tags=["audit"])

ReaderDep = Annotated[Principal, Depends(require(Permission.AUDIT_READ))]
LimitDep = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
OffsetDep = Annotated[int, Query(ge=0)]


@router.get("", response_model=Page[AuditLogRead], summary="Read the audit trail")
async def list_audit_logs(
    session: SessionDep,
    principal: ReaderDep,
    entity_type: AuditEntity | None = None,
    entity_id: uuid.UUID | None = None,
    action: AuditAction | None = None,
    limit: LimitDep = DEFAULT_LIMIT,
    offset: OffsetDep = 0,
) -> Page[AuditLogRead]:
    entries, total = await audit_service.list_audit_logs(
        session,
        principal,
        limit=limit,
        offset=offset,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
    )
    return Page(
        items=[AuditLogRead.model_validate(entry) for entry in entries],
        total=total,
        limit=limit,
        offset=offset,
    )


__all__ = ["router"]
