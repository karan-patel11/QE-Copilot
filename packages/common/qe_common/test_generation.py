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
    """What kind of test a generated case is.

    Wide enough to report the mix §11.5 L857-867 lets a requester ask for.
    Without ``POSITIVE``, ``BOUNDARY`` and ``SECURITY`` there is no way to show
    whether ``include_positive_cases`` / ``include_boundary_cases`` /
    ``include_security_cases`` were honoured — which is the reason ADR-0203 gave
    for adding the ``test_type`` column at all, so the vocabulary has to be able
    to express it (ADR-0211).

    ``BOUNDARY`` and ``EDGE_CASE`` are deliberately distinct: §7.1 L214-215 lists
    "Boundary cases" and "Edge cases" as separate items.

    There is deliberately **no** ``ACCESSIBILITY`` member. ADR-0208 rejects
    ``include_accessibility_cases`` with a 422 at the API boundary, so a case of
    that kind can never reach persistence and a value for it would only invite
    one to be written.
    """

    UNIT = "unit"
    INTEGRATION = "integration"
    POSITIVE = "positive"
    NEGATIVE = "negative"
    BOUNDARY = "boundary"
    EDGE_CASE = "edge_case"
    SECURITY = "security"


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
    """The individual checks in the static validation chain.

    Members are §22.2 L1977-1983's validation levels, in the order the spec
    lists them. Levels 1-6 ship in Phase 2; level 7 is deferred (ADR-0205).
    """

    #: Level 1 — JSON/schema validation.
    SCHEMA = "schema"
    #: Level 2 — required-field validation.
    REQUIRED_FIELDS = "required_fields"
    #: Level 3 — framework syntax validation.
    SYNTAX = "syntax"
    #: Level 4 — import validation.
    IMPORTS = "imports"
    #: Level 5 — duplicate detection.
    DUPLICATE = "duplicate"
    #: Level 6 — safety scanning. A security control rather than an optional
    #: extra: §32.6 L2493 names unsafe generated-code execution as a security
    #: test. Flags constructs, never silently strips them (ADR-0205).
    SAFETY = "safety"
    # TODO(phase-N): SANDBOX_EXECUTION — §22.2 level 7, deferred (ADR-0205)


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
