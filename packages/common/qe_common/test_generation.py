"""Test-generation vocabulary.

Shared by the API, the worker, and the gateway so all three name the same things.
Kept free of ORM and provider imports, like the other ``qe_common`` enums.
"""

from __future__ import annotations

from enum import StrEnum


class SourceType(StrEnum):
    """Where the requirement text came from."""

    REQUIREMENT_TEXT = "requirement_text"
    USER_STORY = "user_story"
    ACCEPTANCE_CRITERIA = "acceptance_criteria"
    # TODO(phase-6): ISSUE (imported from a tracker), PULL_REQUEST


class TestFramework(StrEnum):
    """Target framework for generated code."""

    PYTEST = "pytest"
    # TODO(phase-4+): JEST, JUNIT


class TestType(StrEnum):
    """What kind of test a generated case is."""

    UNIT = "unit"
    INTEGRATION = "integration"
    EDGE_CASE = "edge_case"
    NEGATIVE = "negative"


class TestPriority(StrEnum):
    """Reviewer-facing priority of a generated case."""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class TestCaseStatus(StrEnum):
    """Review state of a generated case.

    Defaults to :attr:`PENDING_REVIEW` everywhere — nothing auto-approves
    (ADR-0203); approval is always an explicit human action.
    """

    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ValidationStatus(StrEnum):
    """Outcome of the static validation chain (ADR-0205).

    ``PASSED`` means the static checks passed — the code parses, its imports
    resolve, and pytest could collect it. It does **not** mean the test passes:
    nothing executes generated code in this phase.
    """

    PASSED = "PASSED"
    FAILED = "FAILED"


class ValidationCheck(StrEnum):
    """The individual checks in the static validation chain."""

    SCHEMA = "schema"
    REQUIRED_FIELDS = "required_fields"
    SYNTAX = "syntax"
    IMPORTS = "imports"
    DISCOVERABILITY = "discoverability"
    DUPLICATE = "duplicate"
    # TODO(phase-N): SANDBOX_EXECUTION — deferred, see ADR-0205


class ModelRunStatus(StrEnum):
    """Outcome of a single provider call."""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    #: The provider's safety classifiers declined the request.
    REFUSED = "REFUSED"


__all__ = [
    "ModelRunStatus",
    "SourceType",
    "TestCaseStatus",
    "TestFramework",
    "TestPriority",
    "TestType",
    "ValidationCheck",
    "ValidationStatus",
]
