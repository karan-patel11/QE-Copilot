"""Job vocabulary and state machine.

Shared by the API, the worker, and the scheduler — one source of truth for what
states exist and which transitions are legal. Persistence lives in
:class:`qe_database.models.Job`; this module stays free of ORM imports so the
rules can be reasoned about, and unit-tested, on their own.
"""

from __future__ import annotations

from enum import StrEnum

from qe_common.errors import JobInvalidStateError


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


class JobKind(StrEnum):
    """Job types the platform can execute.

    Phase 1 ships one real, persisted kind. Feature kinds arrive with the
    features themselves rather than as placeholders that would accept work the
    worker cannot actually do.
    """

    HEALTH_CHECK = "health_check"
    #: §22 test generation, executed by :mod:`qe_test_generation` (ADR-0204).
    TEST_GENERATION = "test_generation"
    #: Re-runs code generation for **one** case (§16.3 L1629, ADR-0212 D3).
    #: A separate kind rather than a flag on the payload, so the worker's
    #: handler table shows at a glance that two different things can run.
    TEST_CASE_REGENERATION = "test_case_regeneration"
    # TODO(phase-3): KNOWLEDGE_INGESTION
    # TODO(phase-5): DEFECT_TRIAGE


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

# Allowed forward transitions, enforced by :func:`assert_transition` in both the
# API and the worker.
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


def assert_transition(current: JobState, target: JobState) -> None:
    """Raise :class:`JobInvalidStateError` unless the transition is permitted."""
    if not can_transition(current, target):
        raise JobInvalidStateError(f"A job cannot move from {current.value} to {target.value}.")


def is_terminal(state: JobState) -> bool:
    """Whether ``state`` is final."""
    return state in TERMINAL_STATES


__all__ = [
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATES",
    "JobKind",
    "JobState",
    "assert_transition",
    "can_transition",
    "is_terminal",
]
