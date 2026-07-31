"""Structured-output schemas, one per pipeline stage (§22, ADR-0207, ADR-0211).

These are the Pydantic models handed to ``generate_structured``, so they are
simultaneously the provider's output contract and the pinned schema the §22.2
level-1 check validates against — one definition, so registry and provider
contracts cannot drift (ADR-0202).

Two shapes here are dictated by the provider rather than the domain, and are
commented where they occur: Groq's ``strict: true`` constrained decoding requires
every object to set ``additionalProperties: false`` (ADR-0210), which makes a
free-form JSON object impossible to populate. Anywhere the domain wants a map,
the wire shape is a list of named entries instead.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from qe_common.test_generation import TestPriority, TestType

#: §22.1's ten decomposition outputs, in spec order. Named here so the "all ten
#: always present" rule is assertable against one list rather than a docstring.
DECOMPOSITION_FIELDS: tuple[str, ...] = (
    "actors",
    "preconditions",
    "actions",
    "business_rules",
    "state_transitions",
    "success_conditions",
    "failure_conditions",
    "data_constraints",
    "security_constraints",
    "integration_dependencies",
)


class StateTransition(BaseModel):
    """One ``{from, to, trigger}`` entry (ADR-0207)."""

    model_config = ConfigDict(populate_by_name=True)

    # ``from`` is a Python keyword, so the field is aliased. The alias is what
    # appears on the wire, which is what ADR-0207 specifies.
    from_state: str = Field(alias="from")
    to: str
    trigger: str


class DataConstraint(BaseModel):
    """One ``{field, constraint}`` entry (ADR-0207)."""

    field: str
    constraint: str


class Decomposition(BaseModel):
    """§22.1's ten outputs. **Every key is required.**

    No field has a default, and that is the whole point: an absent key and an
    empty list mean different things, and only one of them is honest. A model
    that omits ``security_constraints`` has not said there are none — it has said
    nothing. Defaults would silently convert the second into the first, which is
    exactly what ADR-0207 forbids, so a missing key fails validation and the
    stage raises.

    Also carries §22 steps 4 and 5 (ADR-0211 Decision 7): entity and constraint
    extraction is ``actors`` + ``data_constraints`` + ``business_rules`` +
    ``integration_dependencies``; risk identification is ``security_constraints``
    + ``failure_conditions``, jointly.
    """

    actors: list[str]
    preconditions: list[str]
    actions: list[str]
    business_rules: list[str]
    state_transitions: list[StateTransition]
    success_conditions: list[str]
    failure_conditions: list[str]
    data_constraints: list[DataConstraint]
    security_constraints: list[str]
    integration_dependencies: list[str]

    @model_validator(mode="after")
    def _must_have_something_testable(self) -> Decomposition:
        """ADR-0207's one semantic check.

        A requirement that decomposes to no actions *and* no success conditions
        has nothing testable in it. Generating from it would manufacture coverage
        that traces to nothing, so the stage fails and the failure surfaces.
        """
        if not self.actions and not self.success_conditions:
            raise ValueError(
                "Decomposition produced neither actions nor success conditions, so the "
                "requirement contains nothing testable."
            )
        return self


class PlannedCase(BaseModel):
    """One scenario the plan intends to generate (§22 test-plan generation)."""

    title: str
    objective: str
    test_type: TestType
    priority: TestPriority
    #: What in the decomposition this case exists to cover. Keeps every planned
    #: case traceable to the requirement rather than to the model's imagination.
    covers: str


class TestPlan(BaseModel):
    """§22 test-plan generation output."""

    cases: list[PlannedCase]
    #: Gaps the plan knowingly leaves, e.g. "no negative cases: the requirement
    #: states no failure conditions". Reported rather than papered over (ADR-0208).
    coverage_notes: str


class TestDatum(BaseModel):
    """One named input value.

    A list of these rather than a JSON object because ``additionalProperties:
    false`` under strict decoding would otherwise permit only ``{}`` (ADR-0210).
    Collapsed back into a mapping on persistence.
    """

    name: str
    value: str


class TestStep(BaseModel):
    """One ``{action, expected}`` step, as §11.5 L877 displays them."""

    action: str
    expected: str


class GeneratedCase(BaseModel):
    """One fully-specified case — the §22 detailed-test-generation output.

    Field names track ``generated_test_cases`` (§15.6) so persistence is a
    mapping rather than a translation.
    """

    title: str
    objective: str
    preconditions: str
    test_data: list[TestDatum]
    steps: list[TestStep]
    expected_result: str
    priority: TestPriority
    tags: list[str]
    test_type: TestType


class GeneratedCases(BaseModel):
    """The detailed-generation stage's response."""

    cases: list[GeneratedCase]


class GeneratedCode(BaseModel):
    """Pytest source for one case (§38 L2801)."""

    #: Echoed so misalignment between code and case is detectable rather than
    #: assumed away; the pipeline pairs by ordinal and checks this matches.
    title: str
    code: str


class GeneratedCodeSet(BaseModel):
    """The code-generation stage's response, one item per case, in order."""

    items: list[GeneratedCode]


def decomposition_summary(decomposition: Decomposition) -> dict[str, Any]:
    """Cardinalities only — never contents.

    Decomposition is not persisted (ADR-0207's accepted tradeoff), so this is
    what makes its *shape* recoverable from logs. It deliberately carries no
    field values: the requirement is untrusted and potentially sensitive (§26.5),
    and copying it into the log stream would recreate in logs exactly the second
    copy ADR-0207 declined to create in the database.
    """
    return {name: len(getattr(decomposition, name)) for name in DECOMPOSITION_FIELDS}


__all__ = [
    "DECOMPOSITION_FIELDS",
    "DataConstraint",
    "Decomposition",
    "GeneratedCase",
    "GeneratedCases",
    "GeneratedCode",
    "GeneratedCodeSet",
    "PlannedCase",
    "StateTransition",
    "TestDatum",
    "TestPlan",
    "TestStep",
    "decomposition_summary",
]
