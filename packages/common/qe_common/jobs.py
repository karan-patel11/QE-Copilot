"""Job domain model and state machine.

Shared by the worker, scheduler, and API (single source of truth). Phase 0 has
no persistence for jobs — the ``jobs`` table is ``TODO(phase-1)`` — and no real
job logic; this defines the vocabulary the later phases build on.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from enum import StrEnum

from pydantic import BaseModel, Field


class JobState(StrEnum):
    """Lifecycle states for an asynchronous job."""

    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_FOR_PROVIDER = "WAITING_FOR_PROVIDER"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


# Terminal states: a job in one of these never transitions again.
TERMINAL_STATES: frozenset[JobState] = frozenset(
    {
        JobState.COMPLETED,
        JobState.PARTIALLY_COMPLETED,
        JobState.FAILED,
        JobState.CANCELLED,
        JobState.TIMED_OUT,
    }
)

# Allowed forward transitions. Enforced by validators in a later phase; declared
# now so the state machine is documented and testable from Phase 0.
ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.PENDING: frozenset({JobState.QUEUED, JobState.CANCELLED}),
    JobState.QUEUED: frozenset({JobState.RUNNING, JobState.CANCELLED, JobState.TIMED_OUT}),
    JobState.RUNNING: frozenset(
        {
            JobState.WAITING_FOR_PROVIDER,
            JobState.VALIDATING,
            JobState.COMPLETED,
            JobState.PARTIALLY_COMPLETED,
            JobState.FAILED,
            JobState.CANCELLED,
            JobState.TIMED_OUT,
        }
    ),
    JobState.WAITING_FOR_PROVIDER: frozenset(
        {
            JobState.RUNNING,
            JobState.VALIDATING,
            JobState.FAILED,
            JobState.TIMED_OUT,
            JobState.CANCELLED,
        }
    ),
    JobState.VALIDATING: frozenset(
        {JobState.COMPLETED, JobState.PARTIALLY_COMPLETED, JobState.FAILED, JobState.CANCELLED}
    ),
    JobState.COMPLETED: frozenset(),
    JobState.PARTIALLY_COMPLETED: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.CANCELLED: frozenset(),
    JobState.TIMED_OUT: frozenset(),
}


def can_transition(current: JobState, target: JobState) -> bool:
    """Return whether ``current -> target`` is a permitted transition."""
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


class Job(BaseModel):
    """In-memory job representation. TODO(phase-1): back this with the jobs table."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    kind: str = Field(description="Job type discriminator, e.g. 'health_check'.")
    state: JobState = JobState.PENDING
    created_at: _dt.datetime = Field(default_factory=lambda: _dt.datetime.now(_dt.UTC))
    payload: dict[str, object] = Field(default_factory=dict)


__all__ = [
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATES",
    "Job",
    "JobState",
    "can_transition",
]
