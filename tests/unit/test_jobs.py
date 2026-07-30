"""T5 PASS: job state machine vocabulary and transitions."""

from __future__ import annotations

from qe_common.jobs import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    Job,
    JobState,
    can_transition,
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


def test_terminal_states_have_no_transitions() -> None:
    for state in TERMINAL_STATES:
        assert ALLOWED_TRANSITIONS[state] == frozenset()


def test_transition_rules() -> None:
    assert can_transition(JobState.PENDING, JobState.QUEUED)
    assert can_transition(JobState.QUEUED, JobState.RUNNING)
    assert can_transition(JobState.RUNNING, JobState.COMPLETED)
    assert not can_transition(JobState.COMPLETED, JobState.RUNNING)
    assert not can_transition(JobState.PENDING, JobState.COMPLETED)


def test_job_defaults() -> None:
    job = Job(kind="health_check")
    assert job.state is JobState.PENDING
    assert job.kind == "health_check"
