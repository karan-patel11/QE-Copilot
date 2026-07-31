"""The N5 pipeline and **the** sync/async bridge (ADR-0204, ADR-0211 Decision 1).

```
qe_worker.tasks                          (sync Celery)
  ├── run_generation()                   (sync — this module)
  │     └── _bridge(_run_stages())        ← the only asyncio.run in this package
  │           ├── decompose              → gateway call 1
  │           ├── plan_tests             → gateway call 2
  │           ├── generate_cases         → gateway call 3
  │           └── generate_code          → gateway call 4
  └── regenerate_case_code()             (sync — this module)
        └── _bridge(generate_code())      ← same bridge, one call
```

Two properties this layout exists to guarantee:

**One event loop per generation.** Nothing below :func:`run_generation` creates
one. A per-call ``asyncio.run`` would build and tear down a loop for each
provider call, discard whatever connection state the client holds between them,
and serialise the pipeline by construction. Enforced by a test that walks this
package's AST, not by convention.

**The loop contains provider calls only.** Prompt resolution happens before it
and validation/persistence after it, so the only database work inside the loop is
the gateway's own ``model_runs`` write — which is deliberately independent of the
pipeline transaction (Decision 2), so a rollback here cannot erase the record of
a call that was already billed.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from qe_ai_gateway.base import LanguageModelProvider
from qe_common.ai import ModelOperation
from qe_common.errors import AppError, ErrorCode, NotFoundError, TestGenerationError
from qe_common.jobs import JobState, assert_transition
from qe_common.test_generation import TestFramework, TestPriority, TestType
from qe_database.models import GeneratedTestCase, TestGenerationRequest
from qe_observability import bind_log_context, get_logger
from qe_test_generation.config import TestGeneratorConfig, validate_configuration
from qe_test_generation.contracts import (
    Decomposition,
    GeneratedCase,
    GeneratedCases,
    GeneratedCodeSet,
    TestDatum,
    TestPlan,
    TestStep,
    decomposition_summary,
)
from qe_test_generation.persistence import build_summary, persist_cases
from qe_test_generation.stages import (
    GenerationContext,
    ResolvedPrompt,
    decompose,
    generate_cases,
    generate_code,
    plan_tests,
    resolve_prompts,
)
from qe_test_generation.validation import CaseValidation, validate_case

logger = get_logger(__name__)

SessionFactory = Callable[[], Session]

_T = TypeVar("_T")


def _bridge(coroutine: Coroutine[Any, Any, _T]) -> _T:
    """**The** sync/async boundary for this package (ADR-0211 Decision 1).

    Every sync entry point funnels through here, so adding a second one — the
    regeneration path, say — cannot quietly add a second event loop. There is
    exactly one ``asyncio.run`` in the package and this is it; a test walks the
    AST and fails if another appears.
    """
    return asyncio.run(coroutine)


@dataclass(slots=True)
class StageOutputs:
    """What the four provider calls produced, plus their audit ids."""

    decomposition: Decomposition
    plan: TestPlan
    cases: GeneratedCases
    code: GeneratedCodeSet
    model_run_ids: list[uuid.UUID | None] = field(default_factory=list)
    prompt_versions: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GenerationOutcome:
    """The result the worker reports back onto the job row."""

    request_id: uuid.UUID
    state: JobState
    case_count: int
    summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": str(self.request_id),
            "state": self.state.value,
            "case_count": self.case_count,
            "summary": self.summary,
        }


def run_generation(
    session_factory: SessionFactory,
    request_id: uuid.UUID,
    *,
    provider: LanguageModelProvider,
) -> GenerationOutcome:
    """Run one generation end to end. **The sync/async bridge lives here.**

    Takes a session *factory* rather than a session because this function owns
    several distinct transaction boundaries and needs them to be genuinely
    distinct (§37 L2743): the pre-flight read, the persistence transaction that
    must be able to roll back as a unit, and the failure write that must survive
    when it does.
    """
    prompts, context, requirement, config = _preflight(session_factory, request_id)

    try:
        # One loop, four awaits. Nothing below this line opens another.
        outputs = _bridge(
            _run_stages(
                provider,
                prompts=prompts,
                context=context,
                requirement=requirement,
                config=config,
            )
        )
        return _finalise(session_factory, request_id, config=config, outputs=outputs)
    except Exception as exc:
        _mark_failed(session_factory, request_id, exc)
        raise


async def _run_stages(
    provider: LanguageModelProvider,
    *,
    prompts: dict[ModelOperation, ResolvedPrompt],
    context: GenerationContext,
    requirement: str,
    config: TestGeneratorConfig,
) -> StageOutputs:
    """The four §22 provider stages, awaited in order on one loop.

    Sequential because each stage consumes the previous one's output. The one
    natural fan-out — per-case code generation — is deliberately a single call
    instead (ADR-0211 Decision 1).
    """
    decomposed = await decompose(
        provider, prompts=prompts, context=context, requirement=requirement
    )
    # Cardinalities only, never contents: decomposition is not persisted
    # (ADR-0207), so this is what makes its shape recoverable, and the
    # requirement text is untrusted and potentially sensitive (§26.5).
    logger.info(
        "requirement decomposed",
        extra={
            "event_type": "testgen.decomposed",
            "model_run_id": str(decomposed.model_run_id) if decomposed.model_run_id else None,
            "prompt_version": prompts[ModelOperation.REQUIREMENT_DECOMPOSITION].version,
            **{
                f"decomposition.{k}": v for k, v in decomposition_summary(decomposed.output).items()
            },
        },
    )

    planned = await plan_tests(
        provider,
        prompts=prompts,
        context=context,
        decomposition=decomposed.output,
        config=config,
    )
    generated = await generate_cases(
        provider,
        prompts=prompts,
        context=context,
        plan=planned.output,
        decomposition=decomposed.output,
        config=config,
    )
    coded = await generate_code(provider, prompts=prompts, context=context, cases=generated.output)

    return StageOutputs(
        decomposition=decomposed.output,
        plan=planned.output,
        cases=generated.output,
        code=coded.output,
        model_run_ids=[
            decomposed.model_run_id,
            planned.model_run_id,
            generated.model_run_id,
            coded.model_run_id,
        ],
        prompt_versions={operation.value: prompt.version for operation, prompt in prompts.items()},
    )


def _preflight(
    session_factory: SessionFactory, request_id: uuid.UUID
) -> tuple[dict[ModelOperation, ResolvedPrompt], GenerationContext, str, TestGeneratorConfig]:
    """Everything that must succeed before a single billed call is made.

    Config validation, prompt resolution, and the status move all happen here so
    that an unsupported option, an unseeded registry, or a drifted template costs
    nothing (ADR-0208's ceiling principle, applied to failures rather than cost).
    """
    with session_factory() as session:
        request = _load(session, request_id)
        bind_log_context(
            request_id=str(request.id),
            project_id=str(request.project_id),
            job_id=str(request.job_id) if request.job_id else None,
        )

        config = validate_configuration(request.configuration)
        if request.framework != TestFramework.PYTEST.value:
            raise TestGenerationError(
                f"Framework {request.framework!r} is not supported in this phase; "
                f"§38 L2801 scopes it to Pytest code generation."
            )

        prompts = resolve_prompts(session)
        context = GenerationContext(
            organisation_id=request.organisation_id,
            request_id=request.id,
            project_id=request.project_id,
            job_id=request.job_id,
        )
        requirement = request.source_reference

        _advance(request, JobState.RUNNING)
        _advance(request, JobState.WAITING_FOR_PROVIDER)
        # The column is singular (§15.6) but four prompts are involved. The
        # detailed-generation version is recorded here as the primary; all four
        # land in ``summary.prompt_versions`` so none is lost.
        request.prompt_version = prompts[ModelOperation.TEST_GENERATION].version
        session.commit()

    return prompts, context, requirement, config


def _finalise(
    session_factory: SessionFactory,
    request_id: uuid.UUID,
    *,
    config: TestGeneratorConfig,
    outputs: StageOutputs,
) -> GenerationOutcome:
    """Validate, persist, and close out — in one transaction, deliberately.

    Everything here rolls back as a unit if any part of it fails. The
    ``model_runs`` rows for the four calls above do **not**, because they were
    committed independently while the calls happened (ADR-0211 Decision 2) — the
    provider billed for them whether or not this transaction survives.
    """
    codes = _align_code(outputs.cases, outputs.code)

    validations: list[CaseValidation] = []
    seen: list[GeneratedCase] = []
    for case, code in zip(outputs.cases.cases, codes, strict=True):
        validations.append(validate_case(case, code, seen))
        seen.append(case)

    with session_factory() as session:
        request = _load(session, request_id)
        _advance(request, JobState.VALIDATING)

        persist_cases(
            session,
            request=request,
            cases=outputs.cases.cases,
            codes=codes,
            validations=validations,
        )
        summary = build_summary(
            config=config,
            decomposition=outputs.decomposition,
            plan=outputs.plan,
            cases=outputs.cases.cases,
            validations=validations,
            prompt_versions=outputs.prompt_versions,
            model_run_ids=outputs.model_run_ids,
        )
        request.summary = summary
        _advance(request, JobState.COMPLETED)
        session.commit()
        state = JobState(request.status)

    logger.info(
        "test generation completed",
        extra={
            "event_type": "testgen.completed",
            "case_count": summary["case_count"],
            "model_run_ids": summary["model_run_ids"],
        },
    )
    return GenerationOutcome(
        request_id=request_id,
        state=state,
        case_count=summary["case_count"],
        summary=summary,
    )


def _align_code(cases: GeneratedCases, code: GeneratedCodeSet) -> list[str]:
    """Pair each case with its generated code, by ordinal.

    A count mismatch fails the run rather than being papered over with empty
    strings: silently pairing case 3 with case 4's code would persist a test
    whose body tests something else, and nothing downstream could detect it.
    """
    if len(code.items) != len(cases.cases):
        raise TestGenerationError(
            f"Code generation returned {len(code.items)} items for "
            f"{len(cases.cases)} cases; they cannot be paired."
        )
    return [item.code for item in code.items]


def _load(session: Session, request_id: uuid.UUID) -> TestGenerationRequest:
    request = session.scalar(
        select(TestGenerationRequest).where(TestGenerationRequest.id == request_id)
    )
    if request is None:
        raise NotFoundError(f"Test generation request {request_id!s} was not found.")
    return request


def _advance(request: TestGenerationRequest, target: JobState) -> None:
    """Move the request through the *job* state machine — one vocabulary, not two."""
    current = request.job_state
    if current is target:
        return
    assert_transition(current, target)
    request.status = target.value


def _mark_failed(
    session_factory: SessionFactory, request_id: uuid.UUID, exc: BaseException
) -> None:
    """Record the failure on the request row, in its own transaction.

    Its own transaction because the transaction that just failed is the one being
    rolled back — writing the reason into it would roll the reason back too, and
    the request would sit in a non-terminal state with no explanation.

    Never raises: a failure to record the failure must not replace the original
    exception, which is already propagating to the worker. Logged at ERROR
    instead, so nothing is swallowed silently (§37 L2746).
    """
    try:
        with session_factory() as session:
            request = _load(session, request_id)
            if request.job_state not in {JobState.COMPLETED, JobState.FAILED}:
                assert_transition(request.job_state, JobState.FAILED)
                request.status = JobState.FAILED.value
            request.error = f"{type(exc).__name__}: {exc}"
            # Structured, so a client can tell a retryable provider failure from
            # template drift — which no retry fixes — without parsing the
            # message (ADR-0212 Decision 5).
            request.error_code = (
                exc.code.value if isinstance(exc, AppError) else ErrorCode.INTERNAL_ERROR.value
            )
            session.commit()
    except Exception as nested:  # pragma: no cover - defensive
        logger.error(
            "could not record generation failure on the request row",
            exc_info=nested,
            extra={"event_type": "testgen.failure_write_failed", "request_id": str(request_id)},
        )


def regenerate_case_code(
    session_factory: SessionFactory,
    case_id: uuid.UUID,
    *,
    provider: LanguageModelProvider,
) -> GeneratedTestCase:
    """Re-run **code generation only**, for one case (ADR-0212 Decision 3).

    One provider call. The case body — title, objective, steps, expected result —
    is sent unchanged and comes back unchanged: re-running detailed generation
    would silently replace what the reviewer has already read while they believed
    they were asking to fix the code. No other case in the request is touched,
    including its ``human_status``.

    The consequence, stated where callers will read it: this **cannot repair a
    defective case**, only defective code. A case that failed §22.2 level 2 will
    fail again, because the same body is resubmitted.

    The ``model_runs`` row carries the **original** ``request_id``, so cost rolls
    up to the request that owns the case rather than disappearing.
    """
    with session_factory() as session:
        case = _load_case(session, case_id)
        request = _load(session, case.request_id)
        prompts = resolve_prompts(session)
        context = GenerationContext(
            organisation_id=request.organisation_id,
            request_id=request.id,
            project_id=request.project_id,
            job_id=request.job_id,
        )
        original = _case_from_row(case)

    regenerated = _bridge(
        generate_code(
            provider,
            prompts=prompts,
            context=context,
            cases=GeneratedCases(cases=[original]),
        )
    )
    if len(regenerated.output.items) != 1:
        raise TestGenerationError(
            f"Regeneration returned {len(regenerated.output.items)} code items for one case."
        )
    code = regenerated.output.items[0].code

    # Duplicate detection is deliberately not re-run: the case body is unchanged,
    # so its relationship to its siblings cannot have changed. Re-scoring would
    # only add noise, and could relabel a case the reviewer already triaged.
    validation = validate_case(original, code, [])

    with session_factory() as session:
        case = _load_case(session, case_id)
        case.generated_code = code
        case.schema_valid = validation.schema_valid
        case.syntax_valid = validation.syntax_valid
        case.validation_errors = [finding.as_dict() for finding in validation.findings]
        session.commit()
        session.refresh(case)
        logger.info(
            "generated code regenerated",
            extra={
                "event_type": "testgen.regenerated",
                "case_id": str(case_id),
                "request_id": str(case.request_id),
                "model_run_id": str(regenerated.model_run_id) if regenerated.model_run_id else None,
                "valid": validation.schema_valid and validation.syntax_valid,
            },
        )
        return case


def _case_from_row(row: GeneratedTestCase) -> GeneratedCase:
    """Rebuild the stage contract from a persisted row.

    ``test_data`` is stored as the JSONB map the column holds and rebuilt as the
    list-of-pairs the wire schema needs under strict decoding (ADR-0210).
    """
    return GeneratedCase(
        title=row.title,
        objective=row.objective,
        preconditions=row.preconditions or "",
        test_data=[
            TestDatum(name=key, value=str(value)) for key, value in (row.test_data or {}).items()
        ],
        steps=[TestStep.model_validate(step) for step in row.steps],
        expected_result=row.expected_result,
        priority=TestPriority(row.priority),
        tags=list(row.tags),
        test_type=TestType(row.test_type),
    )


def _load_case(session: Session, case_id: uuid.UUID) -> GeneratedTestCase:
    case = session.scalar(select(GeneratedTestCase).where(GeneratedTestCase.id == case_id))
    if case is None:
        raise NotFoundError(f"Generated test case {case_id!s} was not found.")
    return case


def cases_for_request(session: Session, request_id: uuid.UUID) -> list[GeneratedTestCase]:
    """Every generated case for a request, in display order."""
    return list(
        session.scalars(
            select(GeneratedTestCase)
            .where(GeneratedTestCase.request_id == request_id)
            .order_by(GeneratedTestCase.ordinal)
        )
    )


__all__ = [
    "GenerationOutcome",
    "SessionFactory",
    "StageOutputs",
    "cases_for_request",
    "regenerate_case_code",
    "run_generation",
]
