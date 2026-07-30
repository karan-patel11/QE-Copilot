"""Liveness and readiness probes.

``/healthz`` is a pure liveness check — it returns 200 as long as the process is
serving. ``/readyz`` verifies the critical dependencies (Postgres + Redis) and
returns 503 if any is unreachable, so orchestrators route traffic only when the
service can actually do work.
"""

from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter
from sqlalchemy import text
from starlette.responses import JSONResponse

from qe_common.config import get_settings
from qe_database.session import get_async_engine
from qe_observability import get_logger

logger = get_logger("qe_api.health")

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> dict[str, str]:
    """Always 200 while the process is up."""
    return {"status": "ok"}


async def _check_database() -> bool:
    """Whether Postgres answers. Probes must not raise, but must not go quiet
    either: the reason is logged so a failing readiness check is diagnosable."""
    try:
        engine = get_async_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning(
            f"readiness: database unreachable: {exc}",
            extra={"event_type": "readiness.database_down"},
        )
        return False


async def _check_redis() -> bool:
    settings = get_settings()
    client: aioredis.Redis = aioredis.Redis(
        host=settings.redis_host, port=settings.redis_port, db=settings.redis_db
    )
    try:
        return bool(await client.ping())
    except Exception as exc:
        logger.warning(
            f"readiness: redis unreachable: {exc}",
            extra={"event_type": "readiness.redis_down"},
        )
        return False
    finally:
        await client.aclose()


@router.get("/readyz", summary="Readiness probe")
async def readyz() -> JSONResponse:
    """200 when Postgres and Redis are both reachable, else 503."""
    checks = {
        "database": await _check_database(),
        "redis": await _check_redis(),
    }
    healthy = all(checks.values())
    status_code = 200 if healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if healthy else "not_ready",
            "checks": checks,
        },
    )


__all__ = ["router"]
