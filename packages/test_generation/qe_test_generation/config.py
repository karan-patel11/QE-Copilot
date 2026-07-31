"""The eleven Test Generator configuration options (§11.5 L857-867, ADR-0208).

One resolved object, defaults included, is what gets stored in
``test_generation_requests.configuration``: a config that omits
``include_security_cases`` is ambiguous the moment the default changes — it could
mean "the requester declined" or "this request predates the option" — so the
full set is written and every historical request explains itself.

Validation lives here rather than only in the API route so it is enforceable by
direct call, matching §26.2's requirement that checks happen at both the
API-route and the service/business-logic level.
"""

from __future__ import annotations

import decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from qe_common.errors import (
    ErrorDetail,
    TestConfigInvalidError,
    TestConfigUnsupportedError,
)
from qe_common.test_generation import TestFramework, TestPriority, TestType

#: ADR-0208's cap. Not a spec value — §11.5 gives no bound — but a bound is
#: required anyway: the value drives one response's size, and an unbounded
#: request is an unbounded cost and an unbounded latency against §30 L2378.
MAX_NUMBER_OF_TESTS = 20


class TestGeneratorConfig(BaseModel):
    """The eleven options, resolved. Extra keys are rejected, not ignored."""

    model_config = ConfigDict(extra="forbid")

    test_type: TestType = TestType.UNIT
    framework: TestFramework = TestFramework.PYTEST
    target_service: str | None = None
    number_of_tests: int = Field(default=5, ge=1, le=MAX_NUMBER_OF_TESTS)
    include_positive_cases: bool = True
    include_negative_cases: bool = True
    include_boundary_cases: bool = True
    include_security_cases: bool = False
    #: Present in the schema with default ``False`` so the shape does not change
    #: when a later phase implements it — but ``True`` is refused. See
    #: :func:`assert_supported`.
    include_accessibility_cases: bool = False
    desired_priority: TestPriority | None = None
    max_generation_cost_usd: decimal.Decimal | None = None

    @property
    def requested_kinds(self) -> dict[TestType, bool]:
        """Which case kinds were asked for, by the type that would carry them.

        This mapping is why ``TestType`` had to be widened (ADR-0211 Decision 6):
        with only ``NEGATIVE`` representable, three of these four flags could
        never be checked against what actually came back.
        """
        return {
            TestType.POSITIVE: self.include_positive_cases,
            TestType.NEGATIVE: self.include_negative_cases,
            TestType.BOUNDARY: self.include_boundary_cases,
            TestType.SECURITY: self.include_security_cases,
        }


def resolve_configuration(raw: dict[str, Any] | None) -> TestGeneratorConfig:
    """Validate a submitted configuration into the full eleven-key object.

    Raises :class:`TestConfigInvalidError` (422) with per-field details rather
    than letting a malformed value reach the worker, where it would surface as a
    failed job instead of a rejected request.
    """
    try:
        return TestGeneratorConfig.model_validate(raw or {})
    except ValidationError as exc:
        raise TestConfigInvalidError(
            "The test generator configuration is not valid.",
            details=[
                ErrorDetail(
                    field=".".join(str(part) for part in error["loc"]) or None,
                    message=error["msg"],
                )
                for error in exc.errors()
            ],
        ) from exc


def assert_supported(config: TestGeneratorConfig) -> None:
    """Refuse options this phase cannot honour (ADR-0208).

    ``include_accessibility_cases`` is the only one. Accessibility testing needs
    a rendered UI to assert against; this phase generates Pytest from requirement
    text and has no browser, no DOM, and no ruleset. Accepting the flag and
    returning ordinary tests would be worse than refusing it — the requester
    would receive tests labelled as covering accessibility that do not, and the
    flag would sit in ``configuration`` as the record of a promise never kept.

    Raised **before any provider call**, so a refused request costs nothing.
    """
    if config.include_accessibility_cases:
        raise TestConfigUnsupportedError(
            "Accessibility test generation is not supported in this phase: generating "
            "accessibility cases requires a rendered UI to assert against, and this "
            "phase generates Pytest from requirement text only. Re-submit with "
            "include_accessibility_cases set to false.",
            details=[
                ErrorDetail(
                    field="configuration.include_accessibility_cases",
                    message="Unsupported in this phase.",
                )
            ],
        )


def validate_configuration(raw: dict[str, Any] | None) -> TestGeneratorConfig:
    """Resolve and check in one call — the entry point a caller wants."""
    config = resolve_configuration(raw)
    assert_supported(config)
    return config


__all__ = [
    "MAX_NUMBER_OF_TESTS",
    "TestGeneratorConfig",
    "assert_supported",
    "resolve_configuration",
    "validate_configuration",
]
