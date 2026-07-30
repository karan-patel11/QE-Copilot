"""System Health — live status of every runtime component (ADR-0109).

Nothing here is mocked or cached: each call measures the database and Redis, asks
the Celery control plane which workers answer, reads the queue length straight
off the broker, and reads the scheduler's heartbeat key. The API deliberately
does *not* mount the Docker socket to shell out to ``docker ps`` — that would
grant the API container root-equivalent host access for strictly less
information than the control plane already provides.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import time
from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import Any, cast

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from qe_api import API_VERSION
from qe_api.services.jobs import count_jobs_by_state
from qe_auth import Permission, Principal
from qe_common.config import get_settings
from qe_common.health import HealthStatus, worst
from qe_observability import get_logger

logger = get_logger("qe_api.services.system_health")

# Set when the module is first imported, i.e. at process start.
PROCESS_STARTED_AT: _dt.datetime = _dt.datetime.now(_dt.UTC)

# Celery's default queue is a Redis list of this name.
DEFAULT_QUEUE_NAME = "celery"
WORKER_PING_TIMEOUT_SECONDS = 1.0
# Beat ticks every minute; three missed ticks is a real outage, not a blip.
SCHEDULER_STALE_AFTER_SECONDS = 180


@dataclass
class ComponentStatus:
    """One component's live status."""

    status: HealthStatus
    detail: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


def _redis_client() -> aioredis.Redis:
    settings = get_settings()
    return aioredis.Redis(host=settings.redis_host, port=settings.redis_port, db=settings.redis_db)


async def check_database(session: AsyncSession) -> ComponentStatus:
    """Round-trip a trivial query and report the latency."""
    started = time.perf_counter()
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning(f"database health check failed: {exc}", extra={"event_type": "health.db"})
        return ComponentStatus(status=HealthStatus.UNHEALTHY, detail=str(exc))
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return ComponentStatus(status=HealthStatus.HEALTHY, metrics={"latency_ms": latency_ms})


async def check_redis() -> ComponentStatus:
    """PING Redis and report the latency."""
    client = _redis_client()
    started = time.perf_counter()
    try:
        await client.ping()
    except Exception as exc:
        logger.warning(f"redis health check failed: {exc}", extra={"event_type": "health.redis"})
        return ComponentStatus(status=HealthStatus.UNHEALTHY, detail=str(exc))
    finally:
        await client.aclose()
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return ComponentStatus(status=HealthStatus.HEALTHY, metrics={"latency_ms": latency_ms})


async def check_queue() -> ComponentStatus:
    """Read the broker's queue length — the real backlog, not an estimate."""
    client = _redis_client()
    try:
        # redis-py types list commands as ``Awaitable[int] | int`` to share one
        # implementation between its sync and async clients; on this client it is
        # always the awaitable branch.
        depth = int(await cast(Awaitable[int], client.llen(DEFAULT_QUEUE_NAME)))
    except Exception as exc:
        logger.warning(f"queue depth check failed: {exc}", extra={"event_type": "health.queue"})
        return ComponentStatus(status=HealthStatus.UNHEALTHY, detail=str(exc))
    finally:
        await client.aclose()
    return ComponentStatus(
        status=HealthStatus.HEALTHY, metrics={"depth": depth, "queue": DEFAULT_QUEUE_NAME}
    )


def _ping_workers() -> list[str]:
    """Blocking Celery control-plane ping; called via a worker thread."""
    from qe_worker.celery_app import celery_app

    replies = celery_app.control.ping(timeout=WORKER_PING_TIMEOUT_SECONDS) or []
    names: list[str] = []
    for reply in replies:
        names.extend(str(name) for name in reply)
    return sorted(names)


async def check_workers() -> ComponentStatus:
    """Ask the Celery control plane which workers are alive right now."""
    try:
        names = await asyncio.to_thread(_ping_workers)
    except Exception as exc:
        logger.warning(f"worker ping failed: {exc}", extra={"event_type": "health.workers"})
        return ComponentStatus(status=HealthStatus.UNHEALTHY, detail=str(exc))

    if not names:
        return ComponentStatus(
            status=HealthStatus.DEGRADED,
            detail="No worker answered the control-plane ping.",
            metrics={"online": 0, "workers": []},
        )
    return ComponentStatus(
        status=HealthStatus.HEALTHY, metrics={"online": len(names), "workers": names}
    )


async def check_scheduler() -> ComponentStatus:
    """Read the beat heartbeat key; staleness means ticks have stopped."""
    from qe_worker.tasks import SCHEDULER_HEARTBEAT_KEY

    client = _redis_client()
    try:
        raw = await client.get(SCHEDULER_HEARTBEAT_KEY)
    except Exception as exc:
        logger.warning(
            f"scheduler heartbeat read failed: {exc}", extra={"event_type": "health.scheduler"}
        )
        return ComponentStatus(status=HealthStatus.UNHEALTHY, detail=str(exc))
    finally:
        await client.aclose()

    if raw is None:
        return ComponentStatus(
            status=HealthStatus.DEGRADED,
            detail="No scheduler heartbeat has been recorded.",
            metrics={"last_heartbeat_at": None, "seconds_since_heartbeat": None},
        )

    stamped_at = _dt.datetime.fromisoformat(raw.decode() if isinstance(raw, bytes) else str(raw))
    age = (_dt.datetime.now(_dt.UTC) - stamped_at).total_seconds()
    metrics = {
        "last_heartbeat_at": stamped_at.isoformat(),
        "seconds_since_heartbeat": round(age, 1),
    }
    if age > SCHEDULER_STALE_AFTER_SECONDS:
        return ComponentStatus(
            status=HealthStatus.DEGRADED,
            detail=f"The last heartbeat was {round(age)}s ago.",
            metrics=metrics,
        )
    return ComponentStatus(status=HealthStatus.HEALTHY, metrics=metrics)


def check_api() -> ComponentStatus:
    """Uptime and identity of the process serving this request."""
    settings = get_settings()
    uptime = (_dt.datetime.now(_dt.UTC) - PROCESS_STARTED_AT).total_seconds()
    return ComponentStatus(
        status=HealthStatus.HEALTHY,
        metrics={
            "uptime_seconds": round(uptime, 1),
            "started_at": PROCESS_STARTED_AT.isoformat(),
            "environment": settings.environment,
            "version": API_VERSION,
        },
    )


def overall_status(components: dict[str, ComponentStatus]) -> HealthStatus:
    """Worst component wins: a missing dependency is not a healthy system."""
    return worst(component.status for component in components.values())


async def collect(
    session: AsyncSession, principal: Principal
) -> tuple[HealthStatus, dict[str, ComponentStatus], dict[str, int]]:
    """Gather every component's live status concurrently."""
    principal.require(Permission.SYSTEM_READ)

    database, redis_status, queue, workers, scheduler = await asyncio.gather(
        check_database(session),
        check_redis(),
        check_queue(),
        check_workers(),
        check_scheduler(),
    )
    components = {
        "api": check_api(),
        "database": database,
        "redis": redis_status,
        "queue": queue,
        "workers": workers,
        "scheduler": scheduler,
    }
    # Only read job counts when the database answered; otherwise this would
    # raise and turn a *reported* outage into a 500.
    database_ok = database.status is HealthStatus.HEALTHY
    include_jobs = database_ok and principal.has_permission(Permission.JOB_READ)
    jobs = await count_jobs_by_state(session, principal) if include_jobs else {}
    return overall_status(components), components, jobs


__all__ = [
    "PROCESS_STARTED_AT",
    "ComponentStatus",
    "check_api",
    "check_database",
    "check_queue",
    "check_redis",
    "check_scheduler",
    "check_workers",
    "collect",
    "overall_status",
]
