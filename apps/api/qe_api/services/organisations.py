"""Organisation services.

The organisation *is* the tenant boundary, so a request-scoped principal can
only ever see its own (ADR-0106) and cannot provision or destroy tenants from
inside one (ADR-0111) — that is a platform operation, exposed as ``qe org``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qe_api.services.audit import record_audit
from qe_api.services.support import commit_and_refresh, flush_or_conflict
from qe_auth import Permission, Principal
from qe_common.audit import AuditAction, AuditEntity
from qe_common.errors import NotFoundError
from qe_database.models import Organisation


async def get_organisation(
    session: AsyncSession, principal: Principal, organisation_id: uuid.UUID
) -> Organisation:
    """Load an organisation; anything but the caller's own reads as not found."""
    principal.require(Permission.ORGANISATION_READ)
    if organisation_id != principal.organisation_id:
        raise NotFoundError("Organisation not found.")
    stmt = select(Organisation).where(Organisation.id == organisation_id)
    org = (await session.execute(stmt)).scalar_one_or_none()
    if org is None:
        raise NotFoundError("Organisation not found.")
    return org


async def list_organisations(session: AsyncSession, principal: Principal) -> list[Organisation]:
    """Every organisation the caller can see — exactly one, by construction."""
    return [await get_organisation(session, principal, principal.organisation_id)]


async def update_organisation(
    session: AsyncSession,
    principal: Principal,
    organisation_id: uuid.UUID,
    *,
    name: str | None = None,
) -> Organisation:
    """Rename the caller's organisation. The slug is immutable — it is an identifier."""
    principal.require(Permission.ORGANISATION_WRITE)
    org = await get_organisation(session, principal, organisation_id)
    changes: dict[str, object] = {}
    if name is not None:
        changes["name"] = {"from": org.name, "to": name}
        org.name = name

    await flush_or_conflict(session, "Organisation could not be updated.")
    await record_audit(
        session,
        principal,
        action=AuditAction.UPDATE,
        entity_type=AuditEntity.ORGANISATION,
        entity_id=org.id,
        changes=changes,
    )
    return await commit_and_refresh(session, org, "Organisation could not be updated.")


__all__ = ["get_organisation", "list_organisations", "update_organisation"]
