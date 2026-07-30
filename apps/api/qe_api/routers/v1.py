"""Version 1 API router.

Phase 0 exposes only a placeholder ``/ping``. Feature routers (test generation,
defect triage, knowledge base, evaluations, ...) are mounted here in later
phases.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1", tags=["v1"])


class PingResponse(BaseModel):
    """Placeholder liveness echo for the versioned API."""

    message: str = "pong"


@router.get("/ping", response_model=PingResponse, summary="Placeholder ping")
async def ping() -> PingResponse:
    """Return a static pong. TODO(phase-1): replace with real v1 endpoints."""
    return PingResponse()


# TODO(phase-4): mount test-generation router.
# TODO(phase-5): mount defect-triage router.
# TODO(phase-3): mount knowledge-base router.

__all__ = ["router"]
