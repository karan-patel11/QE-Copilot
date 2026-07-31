"""The four provider-calling stages of the §22 pipeline (ADR-0211).

Every stage goes through :mod:`qe_ai_gateway` and never touches a vendor SDK
(§18 L1766, §37 L2745), and every stage's prompt comes from the registry rather
than from a literal here, so ``model_runs.prompt_version_id`` always holds a
string the registry actually issued (ADR-0209 Decision 5).

All four are ``async`` and are awaited inside the single event loop the bridge in
:mod:`qe_test_generation.pipeline` opens. None of them creates a loop.

Stages 4 and 5 of §22 — entity/constraint extraction and risk identification —
are **not** separate stages here: they fold into decomposition's ten-field output
(ADR-0211 Decision 7).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from qe_ai_gateway.base import LanguageModelProvider
from qe_ai_gateway.contracts import (
    SchemaT,
    StructuredGenerationRequest,
    StructuredGenerationResponse,
)
from qe_common.ai import ModelOperation
from qe_prompt_registry import get_active
from qe_prompt_registry.templates import SourceTemplate, get_source_template
from qe_test_generation.config import TestGeneratorConfig
from qe_test_generation.contracts import (
    Decomposition,
    GeneratedCases,
    GeneratedCodeSet,
    TestPlan,
)

#: Prompt name per stage. The registry is keyed by *name*; ``get_active`` resolves
#: it to the single ACTIVE version, whose ``.version`` string is what the gateway
#: records. (Note the signature: ``get_active(session, prompt_name)`` — the name,
#: not the version string.)
PROMPT_NAMES: dict[ModelOperation, str] = {
    ModelOperation.REQUIREMENT_DECOMPOSITION: "decompose",
    ModelOperation.TEST_PLAN: "testplan",
    ModelOperation.TEST_GENERATION: "testgen",
    ModelOperation.PYTEST_CODEGEN: "pytest_codegen",
}


@dataclass(frozen=True, slots=True)
class GenerationContext:
    """Attribution carried onto every ``model_runs`` row for this run."""

    organisation_id: uuid.UUID
    request_id: uuid.UUID
    project_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class ResolvedPrompt:
    """An ACTIVE prompt version paired with its source template."""

    version: str
    template: SourceTemplate


def resolve_prompts(session: Session) -> dict[ModelOperation, ResolvedPrompt]:
    """Resolve all four ACTIVE prompts **before** the event loop opens.

    Deliberately synchronous and deliberately up-front. It keeps registry queries
    out of the async pipeline entirely, and it means a missing or drifted prompt
    fails before a single billed provider call is made rather than half way
    through one.

    Propagates ``PromptVersionNotFoundError`` (nothing seeded — run
    ``qe prompts seed``) and ``PromptTemplateDriftError`` (a registered version no
    longer matches its source template, so the row no longer describes what would
    actually run) unchanged.
    """
    resolved: dict[ModelOperation, ResolvedPrompt] = {}
    for operation, prompt_name in PROMPT_NAMES.items():
        row = get_active(session, prompt_name)
        source = get_source_template(row.version)
        if source is None:  # pragma: no cover - get_active already asserts this
            raise AssertionError(f"Active prompt {row.version!r} has no source template.")
        resolved[operation] = ResolvedPrompt(version=row.version, template=source)
    return resolved


async def _call(
    provider: LanguageModelProvider,
    *,
    prompt: ResolvedPrompt,
    operation: ModelOperation,
    output_schema: type[SchemaT],
    context: GenerationContext,
    variables: dict[str, str],
) -> StructuredGenerationResponse[SchemaT]:
    """One structured call. The gateway owns retry, timing, cost, and metering."""
    request: StructuredGenerationRequest[SchemaT] = StructuredGenerationRequest(
        prompt=prompt.template.render(**variables),
        output_schema=output_schema,
        operation=operation,
        organisation_id=context.organisation_id,
        prompt_version_id=prompt.version,
        project_id=context.project_id,
        job_id=context.job_id,
        request_id=context.request_id,
    )
    return await provider.generate_structured(request)


def _as_json(value: object) -> str:
    """Serialise a stage's output for the next stage's prompt.

    Substituted as a *value*, never re-scanned as a template, so braces inside
    model output stay inert and the content remains data (ADR-0205, ADR-0207).
    """
    return json.dumps(value, indent=2, default=str)


async def decompose(
    provider: LanguageModelProvider,
    *,
    prompts: dict[ModelOperation, ResolvedPrompt],
    context: GenerationContext,
    requirement: str,
) -> StructuredGenerationResponse[Decomposition]:
    """§22 stage 3 — requirement decomposition, plus §22 stages 4 and 5."""
    return await _call(
        provider,
        prompt=prompts[ModelOperation.REQUIREMENT_DECOMPOSITION],
        operation=ModelOperation.REQUIREMENT_DECOMPOSITION,
        output_schema=Decomposition,
        context=context,
        variables={"requirement": requirement},
    )


async def plan_tests(
    provider: LanguageModelProvider,
    *,
    prompts: dict[ModelOperation, ResolvedPrompt],
    context: GenerationContext,
    decomposition: Decomposition,
    config: TestGeneratorConfig,
) -> StructuredGenerationResponse[TestPlan]:
    """§22 stage 6 — test-plan generation."""
    return await _call(
        provider,
        prompt=prompts[ModelOperation.TEST_PLAN],
        operation=ModelOperation.TEST_PLAN,
        output_schema=TestPlan,
        context=context,
        variables={
            "decomposition": _as_json(decomposition.model_dump(by_alias=True)),
            "configuration": _as_json(config.model_dump(mode="json")),
        },
    )


async def generate_cases(
    provider: LanguageModelProvider,
    *,
    prompts: dict[ModelOperation, ResolvedPrompt],
    context: GenerationContext,
    plan: TestPlan,
    decomposition: Decomposition,
    config: TestGeneratorConfig,
) -> StructuredGenerationResponse[GeneratedCases]:
    """§22 stage 7 — detailed test generation."""
    return await _call(
        provider,
        prompt=prompts[ModelOperation.TEST_GENERATION],
        operation=ModelOperation.TEST_GENERATION,
        output_schema=GeneratedCases,
        context=context,
        variables={
            "requirement": _as_json(
                {
                    "plan": plan.model_dump(mode="json"),
                    "decomposition": decomposition.model_dump(by_alias=True),
                    "configuration": config.model_dump(mode="json"),
                }
            )
        },
    )


async def generate_code(
    provider: LanguageModelProvider,
    *,
    prompts: dict[ModelOperation, ResolvedPrompt],
    context: GenerationContext,
    cases: GeneratedCases,
) -> StructuredGenerationResponse[GeneratedCodeSet]:
    """§22 stage 8 — code generation, Pytest (§38 L2801).

    One call covering every case rather than one per case: fewer billed calls
    against the §30 L2378 <90 s target, and no concurrent writers on a
    ``Session`` that is not safe for concurrent use (ADR-0211 Decision 1).
    """
    return await _call(
        provider,
        prompt=prompts[ModelOperation.PYTEST_CODEGEN],
        operation=ModelOperation.PYTEST_CODEGEN,
        output_schema=GeneratedCodeSet,
        context=context,
        variables={"test_cases": _as_json(cases.model_dump(mode="json"))},
    )


__all__ = [
    "PROMPT_NAMES",
    "GenerationContext",
    "ResolvedPrompt",
    "decompose",
    "generate_cases",
    "generate_code",
    "plan_tests",
    "resolve_prompts",
]
