"""T5 unit: the job state machine that both the API and the worker enforce."""

from __future__ import annotations

import itertools

import pytest

from qe_common.errors import JobInvalidStateError
from qe_common.jobs import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    JobKind,
    JobState,
    assert_transition,
    can_transition,
    is_terminal,
)

EXPECTED_STATES = {
    "PENDING",
    "QUEUED",
    "RUNNING",
    "WAITING_FOR_PROVIDER",
    "VALIDATING",
    "COMPLETED",
    "PARTIALLY_COMPLETED",
    "FAILED",
    "CANCELLED",
    "TIMED_OUT",
}


def test_all_states_present() -> None:
    assert {s.value for s in JobState} == EXPECTED_STATES


def test_every_state_has_a_transition_rule() -> None:
    """A state missing from the table would silently permit nothing."""
    assert set(ALLOWED_TRANSITIONS) == set(JobState)


def test_terminal_states_have_no_transitions() -> None:
    for state in TERMINAL_STATES:
        assert ALLOWED_TRANSITIONS[state] == frozenset()
        assert is_terminal(state)


def test_non_terminal_states_are_not_terminal() -> None:
    assert not is_terminal(JobState.PENDING)
    assert not is_terminal(JobState.RUNNING)


def test_transition_rules() -> None:
    assert can_transition(JobState.PENDING, JobState.QUEUED)
    assert can_transition(JobState.QUEUED, JobState.RUNNING)
    assert can_transition(JobState.RUNNING, JobState.COMPLETED)
    assert not can_transition(JobState.COMPLETED, JobState.RUNNING)
    assert not can_transition(JobState.PENDING, JobState.COMPLETED)


def test_the_happy_path_is_walkable_end_to_end() -> None:
    path = [JobState.PENDING, JobState.QUEUED, JobState.RUNNING, JobState.COMPLETED]
    for current, target in itertools.pairwise(path):
        assert_transition(current, target)


def test_assert_transition_rejects_an_illegal_move() -> None:
    with pytest.raises(JobInvalidStateError, match="COMPLETED to RUNNING"):
        assert_transition(JobState.COMPLETED, JobState.RUNNING)


def test_a_job_can_always_be_cancelled_before_it_finishes() -> None:
    for state in JobState:
        if state in TERMINAL_STATES:
            continue
        assert can_transition(state, JobState.CANCELLED), state


def test_only_implemented_kinds_are_declared() -> None:
    """A declared kind must have a handler behind it.

    The point of pinning this set is that a kind the worker cannot execute would
    still be accepted by the API and then fail at run time. Phase 1 shipped
    ``health_check``; Phase 2 adds ``test_generation`` (ADR-0204) and
    ``test_case_regeneration`` (ADR-0212 D3). Future kinds stay ``TODO``
    comments in :class:`JobKind` until their handler exists.
    """
    assert {kind.value for kind in JobKind} == {
        "health_check",
        "test_generation",
        "test_case_regeneration",
    }
