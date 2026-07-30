"""Organisation routes.

Tenant provisioning and deletion are deliberately absent: they cannot be
performed from inside a tenant-scoped request (ADR-0111). Use ``qe org``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from qe_api.dependencies import SessionDep, require
from qe_api.schemas import OrganisationRead, OrganisationUpdate
from qe_api.services import organisations as org_service
from qe_auth import Permission, Principal

router = APIRouter(prefix="/organisations", tags=["organisations"])

ReaderDep = Annotated[Principal, Depends(require(Permission.ORGANISATION_READ))]
WriterDep = Annotated[Principal, Depends(require(Permission.ORGANISATION_WRITE))]


@router.get(
    "",
    response_model=list[OrganisationRead],
    summary="List organisations visible to the caller",
)
async def list_organisations(session: SessionDep, principal: ReaderDep) -> list[OrganisationRead]:
    rows = await org_service.list_organisations(session, principal)
    return [OrganisationRead.model_validate(row) for row in rows]


@router.get("/{organisation_id}", response_model=OrganisationRead, summary="Fetch an organisation")
async def get_organisation(
    organisation_id: uuid.UUID, session: SessionDep, principal: ReaderDep
) -> OrganisationRead:
    org = await org_service.get_organisation(session, principal, organisation_id)
    return OrganisationRead.model_validate(org)


@router.patch(
    "/{organisation_id}", response_model=OrganisationRead, summary="Rename an organisation"
)
async def update_organisation(
    organisation_id: uuid.UUID,
    payload: OrganisationUpdate,
    session: SessionDep,
    principal: WriterDep,
) -> OrganisationRead:
    org = await org_service.update_organisation(
        session, principal, organisation_id, name=payload.name
    )
    return OrganisationRead.model_validate(org)


__all__ = ["router"]
