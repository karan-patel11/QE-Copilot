"""N3 unit: the prompt-version lifecycle and version-string format (ADR-0209).

DB-free: the state machine and the format rules live in :mod:`qe_common.prompts`
precisely so they can be exercised without Postgres, the same split
:mod:`qe_common.jobs` uses.
"""

from __future__ import annotations

import itertools

import pytest

from qe_common.errors import PromptVersionFormatError, PromptVersionInvalidStateError
from qe_common.prompts import (
    ALLOWED_TRANSITIONS,
    MAX_VERSION_LENGTH,
    PROMPT_STATUS_ORDER,
    PromptStatus,
    assert_transition,
    assert_version_matches_name,
    build_version,
    can_transition,
    is_terminal,
    parse_version,
)

# The seven stages of §19 L1791-1807, in spec order.
EXPECTED_STATUSES = [
    "DRAFT",
    "OFFLINE_EVALUATION",
    "REVIEW",
    "STAGING",
    "LIMITED_RELEASE",
    "ACTIVE",
    "DEPRECATED",
]


def test_seven_stages_present_in_spec_order() -> None:
    assert [s.value for s in PROMPT_STATUS_ORDER] == EXPECTED_STATUSES
    assert {s.value for s in PromptStatus} == set(EXPECTED_STATUSES)


def test_each_stage_advances_to_exactly_its_successor() -> None:
    for current, expected_next in itertools.pairwise(PROMPT_STATUS_ORDER):
        assert ALLOWED_TRANSITIONS[current] == frozenset({expected_next})


def test_deprecated_is_terminal() -> None:
    assert ALLOWED_TRANSITIONS[PromptStatus.DEPRECATED] == frozenset()
    assert is_terminal(PromptStatus.DEPRECATED)
    assert not any(is_terminal(s) for s in PROMPT_STATUS_ORDER[:-1])


def test_draft_cannot_jump_straight_to_active() -> None:
    """The headline rejection: nothing skips evaluation, review, and staging."""
    assert not can_transition(PromptStatus.DRAFT, PromptStatus.ACTIVE)
    with pytest.raises(PromptVersionInvalidStateError, match="DRAFT to ACTIVE"):
        assert_transition(PromptStatus.DRAFT, PromptStatus.ACTIVE)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (PromptStatus.ACTIVE, PromptStatus.STAGING),
        (PromptStatus.DEPRECATED, PromptStatus.ACTIVE),
        (PromptStatus.REVIEW, PromptStatus.DRAFT),
        (PromptStatus.STAGING, PromptStatus.OFFLINE_EVALUATION),
    ],
)
def test_backward_transitions_are_rejected(current: PromptStatus, target: PromptStatus) -> None:
    """No rollback edges — a rejected version is superseded, not reopened."""
    with pytest.raises(PromptVersionInvalidStateError):
        assert_transition(current, target)


@pytest.mark.parametrize("status", list(PromptStatus))
def test_self_transitions_are_rejected(status: PromptStatus) -> None:
    with pytest.raises(PromptVersionInvalidStateError):
        assert_transition(status, status)


def test_every_illegal_pair_is_rejected() -> None:
    """Exhaustive: only the six forward edges are permitted, out of 49 pairs."""
    legal = {(a, b) for a, targets in ALLOWED_TRANSITIONS.items() for b in targets}
    assert len(legal) == 6
    pairs: list[tuple[PromptStatus, PromptStatus]] = [
        (current, target) for current in PROMPT_STATUS_ORDER for target in PROMPT_STATUS_ORDER
    ]
    assert len(pairs) == 49
    for current, target in pairs:
        if (current, target) in legal:
            assert_transition(current, target)  # must not raise
        else:
            with pytest.raises(PromptVersionInvalidStateError):
                assert_transition(current, target)


# --- version string format (the ADR-0203 hazard surface) --------------------


@pytest.mark.parametrize(
    ("version", "name", "number"),
    [
        ("testgen-v1", "testgen", 1),
        ("testgen-v42", "testgen", 42),
        ("decompose-v1", "decompose", 1),
        ("code_gen-v7", "code_gen", 7),
    ],
)
def test_valid_versions_parse(version: str, name: str, number: int) -> None:
    assert parse_version(version) == (name, number)


@pytest.mark.parametrize(
    "version",
    [
        "testgen",  # no version suffix
        "testgen-v",  # no number
        "testgen-v0",  # zero is not a version
        "testgen-v01",  # leading zero
        "testgen-v1.2",  # not an integer
        "Testgen-v1",  # uppercase name
        "1testgen-v1",  # name must start with a letter
        "testgen-V1",  # uppercase v
        "testgen v1",  # space
        "",  # empty
        "-v1",  # no name
        "testgen-v1-v2",  # two suffixes
    ],
)
def test_malformed_versions_are_rejected(version: str) -> None:
    with pytest.raises(PromptVersionFormatError):
        parse_version(version)


def test_version_longer_than_the_column_is_rejected() -> None:
    """String(64) in both prompt_versions.version and model_runs.prompt_version_id."""
    too_long = "a" * MAX_VERSION_LENGTH + "-v1"
    assert len(too_long) > MAX_VERSION_LENGTH
    with pytest.raises(PromptVersionFormatError, match="exceeds"):
        parse_version(too_long)


def test_version_must_belong_to_its_prompt() -> None:
    """A version citing another prompt would misattribute every model_runs row."""
    assert_version_matches_name("testgen", "testgen-v3")  # must not raise
    with pytest.raises(PromptVersionFormatError, match="does not belong"):
        assert_version_matches_name("testgen", "codegen-v1")


def test_build_version_round_trips() -> None:
    assert build_version("testgen", 3) == "testgen-v3"
    assert parse_version(build_version("testgen", 3)) == ("testgen", 3)


@pytest.mark.parametrize("number", [0, -1])
def test_build_version_rejects_non_positive_numbers(number: int) -> None:
    with pytest.raises(PromptVersionFormatError):
        build_version("testgen", number)
