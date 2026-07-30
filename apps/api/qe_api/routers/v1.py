"""Version 1 API router.

Phase 0 exposes only a placeholder ``/ping``. Feature routers (test generation,
defect triage, knowledge base, evaluations, ...) are mounted here in later
phases.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from qe_api.routers import auth as auth_routes
from qe_api.routers import users as user_routes
from qe_common.config import get_settings

router = APIRouter(prefix="/api/v1", tags=["v1"])


class PingResponse(BaseModel):
    """Placeholder liveness echo for the versioned API."""

    message: str = "pong"


@router.get("/ping", response_model=PingResponse, summary="Placeholder ping")
async def ping() -> PingResponse:
    """Unauthenticated liveness echo for the versioned API."""
    return PingResponse()


router.include_router(auth_routes.router)
router.include_router(user_routes.router)
router.include_router(user_routes.roles_router)

# The dev identity provider is mounted only when explicitly enabled, so it never
# exists — not even in the OpenAPI document — in a non-dev deployment (ADR-0101).
if get_settings().auth_dev_mode:
    router.include_router(auth_routes.dev_router)

# TODO(phase-4): mount test-generation router.
# TODO(phase-5): mount defect-triage router.
# TODO(phase-3): mount knowledge-base router.

__all__ = ["router"]
