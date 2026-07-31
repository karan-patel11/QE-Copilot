"""Prompt-version vocabulary and lifecycle state machine (ADR-0209).

The seven stages come from design-spec §19 L1791-1807. Persistence lives in
:class:`qe_database.models.PromptVersion`; this module stays free of ORM imports
so the rules can be reasoned about, and unit-tested, on their own — the same
split :mod:`qe_common.jobs` uses for the job state machine.

The database enforces the *set* of legal values through a CHECK constraint; this
module enforces the *ordering* between them. A CHECK sees only the row being
written, never the row it replaces, so it structurally cannot express
"DRAFT -> ACTIVE is illegal" (ADR-0209 Decision 3).
"""

from __future__ import annotations

import re
from enum import StrEnum

from qe_common.errors import PromptVersionFormatError, PromptVersionInvalidStateError


class PromptStatus(StrEnum):
    """The seven lifecycle stages of a prompt version (§19 L1791-1807)."""

    DRAFT = "DRAFT"
    OFFLINE_EVALUATION = "OFFLINE_EVALUATION"
    REVIEW = "REVIEW"
    STAGING = "STAGING"
    LIMITED_RELEASE = "LIMITED_RELEASE"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


#: The stages in spec order. The CHECK constraint in migration 0006 is generated
#: from this same tuple, so the database vocabulary cannot drift from the enum.
PROMPT_STATUS_ORDER: tuple[PromptStatus, ...] = (
    PromptStatus.DRAFT,
    PromptStatus.OFFLINE_EVALUATION,
    PromptStatus.REVIEW,
    PromptStatus.STAGING,
    PromptStatus.LIMITED_RELEASE,
    PromptStatus.ACTIVE,
    PromptStatus.DEPRECATED,
)

#: Only :attr:`PromptStatus.DEPRECATED` is terminal. A version that was rejected
#: mid-pipeline simply stops advancing — ADR-0209 keeps no backward edges,
#: because versions are immutable and the answer to a rejection is a new version.
TERMINAL_STATUSES: frozenset[PromptStatus] = frozenset({PromptStatus.DEPRECATED})

#: Forward, one step at a time. Derived from :data:`PROMPT_STATUS_ORDER` so the
#: table and the order can never disagree.
ALLOWED_TRANSITIONS: dict[PromptStatus, frozenset[PromptStatus]] = {
    current: frozenset({PROMPT_STATUS_ORDER[index + 1]})
    for index, current in enumerate(PROMPT_STATUS_ORDER[:-1])
} | {PromptStatus.DEPRECATED: frozenset()}


#: ``{prompt_name}-v{n}``: a lowercase prompt name, then ``-v`` and a positive
#: integer with no leading zero. This is the exact string
#: ``model_runs.prompt_version_id`` holds (ADR-0203 hazard, ADR-0209 Decision 2).
VERSION_PATTERN = re.compile(r"^([a-z][a-z0-9_]*)-v([1-9][0-9]*)$")

#: ``prompt_versions.version`` and ``model_runs.prompt_version_id`` are both
#: ``String(64)``; a version longer than that would be silently truncated by one
#: and rejected by the other.
MAX_VERSION_LENGTH = 64


def can_transition(current: PromptStatus, target: PromptStatus) -> bool:
    """Return whether ``current -> target`` is a permitted transition."""
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def assert_transition(current: PromptStatus, target: PromptStatus) -> None:
    """Raise :class:`PromptVersionInvalidStateError` unless the move is legal."""
    if not can_transition(current, target):
        raise PromptVersionInvalidStateError(
            f"A prompt version cannot move from {current.value} to {target.value}."
        )


def is_terminal(status: PromptStatus) -> bool:
    """Whether ``status`` is final."""
    return status in TERMINAL_STATUSES


def parse_version(version: str) -> tuple[str, int]:
    """Split a version string into ``(prompt_name, number)``.

    Raises :class:`PromptVersionFormatError` if it does not match
    :data:`VERSION_PATTERN`.
    """
    if len(version) > MAX_VERSION_LENGTH:
        raise PromptVersionFormatError(
            f"Prompt version {version!r} exceeds {MAX_VERSION_LENGTH} characters."
        )
    match = VERSION_PATTERN.match(version)
    if match is None:
        raise PromptVersionFormatError(
            f"Prompt version {version!r} is not of the form '{{prompt_name}}-v{{n}}'."
        )
    return match.group(1), int(match.group(2))


def assert_version_matches_name(prompt_name: str, version: str) -> None:
    """Raise unless ``version`` is well-formed *and* belongs to ``prompt_name``.

    A row claiming ``prompt_name="testgen"`` with ``version="codegen-v1"`` would
    make ``model_runs.prompt_version_id`` point at a prompt it did not come from,
    which the future foreign-key backfill (ADR-0209 Decision 2) could not resolve.
    """
    embedded_name, _ = parse_version(version)
    if embedded_name != prompt_name:
        raise PromptVersionFormatError(
            f"Prompt version {version!r} does not belong to prompt {prompt_name!r}."
        )


def build_version(prompt_name: str, number: int) -> str:
    """Compose a version string, validating the result before returning it."""
    if number < 1:
        raise PromptVersionFormatError(
            f"Prompt version numbers start at 1; got {number} for {prompt_name!r}."
        )
    version = f"{prompt_name}-v{number}"
    assert_version_matches_name(prompt_name, version)
    return version


__all__ = [
    "ALLOWED_TRANSITIONS",
    "MAX_VERSION_LENGTH",
    "PROMPT_STATUS_ORDER",
    "TERMINAL_STATUSES",
    "VERSION_PATTERN",
    "PromptStatus",
    "assert_transition",
    "assert_version_matches_name",
    "build_version",
    "can_transition",
    "is_terminal",
    "parse_version",
]
