"""Shared health vocabulary.

Lives beside the other cross-service enums so the service layer, the wire
schema, and the frontend all name the same three states.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class HealthStatus(StrEnum):
    """How a component — or the platform as a whole — is doing."""

    HEALTHY = "healthy"
    #: Serving, but something is wrong: e.g. no worker is answering.
    DEGRADED = "degraded"
    #: A hard dependency is unreachable.
    UNHEALTHY = "unhealthy"


#: Least severe first, so ``max`` over this ordering picks the status to report.
SEVERITY_ORDER: tuple[HealthStatus, ...] = (
    HealthStatus.HEALTHY,
    HealthStatus.DEGRADED,
    HealthStatus.UNHEALTHY,
)


def worst(statuses: Iterable[HealthStatus]) -> HealthStatus:
    """Return the most severe status in ``statuses`` (healthy when empty)."""
    found = list(statuses)
    if not found:
        return HealthStatus.HEALTHY
    return max(found, key=SEVERITY_ORDER.index)


__all__ = ["SEVERITY_ORDER", "HealthStatus", "worst"]
