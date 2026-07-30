"""System Health route.

Distinct from ``/healthz`` and ``/readyz``: those are unauthenticated probes for
orchestrators and answer only "should traffic reach me?". This endpoint is the
authenticated operator view backing the System Health page.
"""

from __future__ import annotations

import datetime as _dt
from typing import Annotated

from fastapi import APIRouter, Depends

from qe_api.dependencies import SessionDep, require
from qe_api.schemas import ComponentHealth, SystemHealthResponse
from qe_api.services import system_health as health_service
from qe_auth import Permission, Principal

router = APIRouter(prefix="/system-health", tags=["system"])

ReaderDep = Annotated[Principal, Depends(require(Permission.SYSTEM_READ))]


@router.get("", response_model=SystemHealthResponse, summary="Live platform health")
async def system_health(session: SessionDep, principal: ReaderDep) -> SystemHealthResponse:
    """Measure every component now and return the result."""
    status, components, jobs = await health_service.collect(session, principal)
    return SystemHealthResponse(
        status=status,
        checked_at=_dt.datetime.now(_dt.UTC),
        components={
            name: ComponentHealth(
                status=component.status,
                detail=component.detail,
                metrics=component.metrics,
            )
            for name, component in components.items()
        },
        jobs=jobs,
    )


__all__ = ["router"]
