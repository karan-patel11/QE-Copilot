"""Test-generation services (§16.3, ADR-0212).

The load-bearing function here is :func:`create_generation_request`, and the
reason is Decision 1: the request row and its job row are written in **one**
transaction which **commits before dispatch**. ``CommittingModelRunRecorder``
writes ``model_runs`` on a separate connection (ADR-0211 Decision 2), so if those
foreign-key targets are not durable by the time the worker makes its first
provider call, every metering write fails its constraint — silently, with nothing
going red.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from qe_api.services.audit import record_audit
from qe_api.services.projects import get_project
from qe_api.services.support import DEFAULT_LIMIT, commit_or_conflict, flush_or_conflict
from qe_auth import Permission, Principal
from qe_common.audit import AuditAction, AuditEntity
from qe_common.errors import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
)
from qe_common.jobs import JobKind, JobState, assert_transition, is_terminal
from qe_common.test_generation import SourceType, TestCaseStatus, TestFramework
from qe_database.models import GeneratedTestCase, Job, TestGenerationRequest
from qe_observability import get_logger
from qe_test_generation import validate_configuration
from qe_test_generation.contracts import GeneratedCase, TestDatum, TestStep
from qe_test_generation.validation import validate_case

logger = get_logger("qe_api.services.test_generation")

RUN_JOB_TASK = "qe_worker.run_job"


async def create_generation_request(
    session: AsyncSession,
    principal: Principal,
    *,
    project_id: uuid.UUID,
    title: str,
    source_type: SourceType,
    source_reference: str,
    framework: TestFramework,
    configuration: dict[str, Any],
    repository_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
) -> tuple[TestGenerationRequest, bool]:
    """Create a request and its job, then dispatch. Returns ``(row, created)``.

    ``created`` is ``False`` when an idempotency key matched an existing request,
    in which case nothing was written and the original row is returned.
    """
    principal.require(Permission.TEST_GENERATION_CREATE)

    # ── Decision 2: validate before anything is written ────────────────────
    # Raises TestConfigUnsupportedError (422) for options this phase refuses, so
    # a rejected request never becomes a row, a job, or a provider call.
    resolved = validate_configuration(configuration)

    # 404s for another tenant's project, before any write.
    await get_project(session, principal, project_id)

    if idempotency_key:
        existing = await _find_by_idempotency_key(session, principal, idempotency_key)
        if existing is not None:
            logger.info(
                "idempotent replay returned the original request",
                extra={"event_type": "testgen.idempotent_replay"},
            )
            return existing, False

    # ── Decision 1: one transaction ────────────────────────────────────────
    request = TestGenerationRequest(
        organisation_id=principal.organisation_id,
        project_id=project_id,
        repository_id=repository_id,
        user_id=principal.user_id,
        title=title,
        source_type=source_type.value,
        source_reference=source_reference,
        framework=framework.value,
        status=JobState.PENDING.value,
        # The full eleven keys, defaults included, so a historical request
        # explains itself even after a default changes (ADR-0208).
        configuration=resolved.model_dump(mode="json"),
        idempotency_key=idempotency_key,
    )
    session.add(request)
    # Flush, not commit: the id exists for the job payload while both rows are
    # still in the same uncommitted transaction.
    await flush_or_conflict(session, "A request with that idempotency key already exists.")

    job = Job(
        organisation_id=principal.organisation_id,
        project_id=project_id,
        created_by=principal.user_id,
        kind=JobKind.TEST_GENERATION.value,
        state=JobState.PENDING.value,
        payload={"request_id": str(request.id)},
    )
    session.add(job)
    await flush_or_conflict(session, "The generation job could not be created.")

    request.job_id = job.id
    assert_transition(JobState(job.state), JobState.QUEUED)
    job.state = JobState.QUEUED.value
    job.queued_at = _dt.datetime.now(_dt.UTC)
    assert_transition(request.job_state, JobState.QUEUED)
    request.status = JobState.QUEUED.value

    await record_audit(
        session,
        principal,
        action=AuditAction.CREATE,
        entity_type=AuditEntity.TEST_GENERATION_REQUEST,
        entity_id=request.id,
        # Deliberately not the requirement text: it is untrusted and potentially
        # sensitive, and the audit trail is not a second place to keep it (§26.5).
        changes={"project_id": str(project_id), "framework": framework.value},
    )

    # ── The commit point. Both rows durable here, nothing dispatched yet. ───
    await commit_or_conflict(session, "A request with that idempotency key already exists.")

    try:
        task_id = _dispatch(job.id)
    except Exception as exc:
        # The rows are already durable, so the failure is recorded rather than
        # rolled back: a request that exists but was never queued is the honest
        # record of what happened.
        job.state = JobState.FAILED.value
        job.error = f"Could not be dispatched to the queue: {exc}"
        job.finished_at = _dt.datetime.now(_dt.UTC)
        request.status = JobState.FAILED.value
        request.error = f"Could not be dispatched to the queue: {exc}"
        request.error_code = "SERVICE_UNAVAILABLE"
        await commit_or_conflict(session, "The request could not be marked failed.")
        logger.error(
            "generation dispatch failed",
            exc_info=exc,
            extra={"event_type": "testgen.dispatch_failed"},
        )
        raise ServiceUnavailableError(
            "The job queue is unavailable; the generation was not started."
        ) from exc

    job.celery_task_id = task_id
    await commit_or_conflict(session, "The job could not be updated.")
    logger.info("generation request queued", extra={"event_type": "testgen.queued"})
    return request, True


def _dispatch(job_id: uuid.UUID) -> str:
    from qe_worker.celery_app import celery_app

    return str(celery_app.send_task(RUN_JOB_TASK, args=[str(job_id)]).id)


async def _find_by_idempotency_key(
    session: AsyncSession, principal: Principal, key: str
) -> TestGenerationRequest | None:
    stmt = select(TestGenerationRequest).where(
        TestGenerationRequest.organisation_id == principal.organisation_id,
        TestGenerationRequest.idempotency_key == key,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_request(
    session: AsyncSession, principal: Principal, request_id: uuid.UUID
) -> TestGenerationRequest:
    """Load one request from the caller's organisation.

    404 rather than 403 for another tenant's row, so existence is not disclosed
    across tenants (ADR-0106).
    """
    principal.require(Permission.TEST_GENERATION_READ)
    stmt = select(TestGenerationRequest).where(
        TestGenerationRequest.id == request_id,
        TestGenerationRequest.organisation_id == principal.organisation_id,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Test generation request not found.")
    return row


async def list_cases(
    session: AsyncSession,
    principal: Principal,
    request_id: uuid.UUID,
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[GeneratedTestCase], int]:
    """Cases for one request, in display order."""
    await get_request(session, principal, request_id)
    stmt = select(GeneratedTestCase).where(GeneratedTestCase.request_id == request_id)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        (
            await session.execute(
                stmt.order_by(GeneratedTestCase.ordinal).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total


async def get_case(
    session: AsyncSession, principal: Principal, case_id: uuid.UUID
) -> GeneratedTestCase:
    principal.require(Permission.TEST_GENERATION_READ)
    stmt = select(GeneratedTestCase).where(
        GeneratedTestCase.id == case_id,
        GeneratedTestCase.organisation_id == principal.organisation_id,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Generated test case not found.")
    return row


async def review_case(
    session: AsyncSession,
    principal: Principal,
    case_id: uuid.UUID,
    *,
    decision: TestCaseStatus,
    note: str | None = None,
) -> GeneratedTestCase:
    """Approve or reject one case — always an explicit human action (§8.2).

    Audited with before/after state, because the review decision is the record of
    who took responsibility for the test.
    """
    principal.require(Permission.TEST_CASE_REVIEW)
    case = await get_case(session, principal, case_id)

    if case.human_status == decision.value:
        raise ConflictError(f"The case is already {decision.value}.")

    before = case.human_status
    case.human_status = decision.value
    case.reviewed_by = principal.user_id
    case.reviewed_at = _dt.datetime.now(_dt.UTC)

    await record_audit(
        session,
        principal,
        action=AuditAction.UPDATE,
        entity_type=AuditEntity.GENERATED_TEST_CASE,
        entity_id=case.id,
        changes={
            "human_status": {"before": before, "after": decision.value},
            "request_id": str(case.request_id),
            "note": note,
        },
    )
    await commit_or_conflict(session, "The review could not be recorded.")
    await session.refresh(case)
    return case


async def revalidate_case(
    session: AsyncSession, principal: Principal, case_id: uuid.UUID
) -> GeneratedTestCase:
    """Re-run the §22.2 static chain against the stored code.

    Synchronous: it makes no provider call, so §13.1 applies rather than §13.2
    (ADR-0204). Nothing here executes the code — ``ast.parse`` only.
    """
    principal.require(Permission.TEST_CASE_REVIEW)
    case = await get_case(session, principal, case_id)

    result = validate_case(_case_from_row(case), case.generated_code, [])
    case.schema_valid = result.schema_valid
    case.syntax_valid = result.syntax_valid
    case.validation_errors = [finding.as_dict() for finding in result.findings]
    await commit_or_conflict(session, "Validation could not be recorded.")
    await session.refresh(case)
    return case


async def regenerate_case(
    session: AsyncSession, principal: Principal, case_id: uuid.UUID
) -> tuple[GeneratedTestCase, Job]:
    """Queue a code-only regeneration for one case (ADR-0212 Decision 3).

    Asynchronous because it calls the provider, so it returns 202 + a job id like
    every other provider-backed operation.
    """
    principal.require(Permission.TEST_GENERATION_CREATE)
    case = await get_case(session, principal, case_id)
    request = await get_request(session, principal, case.request_id)

    if not is_terminal(request.job_state):
        raise ConflictError(
            "The generation for this request has not finished; regenerate once it is terminal."
        )

    job = Job(
        organisation_id=principal.organisation_id,
        project_id=request.project_id,
        created_by=principal.user_id,
        kind=JobKind.TEST_CASE_REGENERATION.value,
        state=JobState.PENDING.value,
        payload={"case_id": str(case.id), "request_id": str(request.id)},
    )
    session.add(job)
    await flush_or_conflict(session, "The regeneration job could not be created.")

    assert_transition(JobState(job.state), JobState.QUEUED)
    job.state = JobState.QUEUED.value
    job.queued_at = _dt.datetime.now(_dt.UTC)

    await record_audit(
        session,
        principal,
        action=AuditAction.UPDATE,
        entity_type=AuditEntity.GENERATED_TEST_CASE,
        entity_id=case.id,
        changes={"action": "regenerate", "request_id": str(request.id), "job_id": str(job.id)},
    )
    # Same rule as Decision 1: durable before dispatch.
    await commit_or_conflict(session, "The regeneration could not be queued.")

    try:
        job.celery_task_id = _dispatch(job.id)
    except Exception as exc:
        job.state = JobState.FAILED.value
        job.error = f"Could not be dispatched to the queue: {exc}"
        await commit_or_conflict(session, "The job could not be marked failed.")
        raise ServiceUnavailableError(
            "The job queue is unavailable; the regeneration was not started."
        ) from exc

    await commit_or_conflict(session, "The job could not be updated.")
    return case, job


def _case_from_row(row: GeneratedTestCase) -> GeneratedCase:
    """Rebuild the stage contract from a persisted row (mirrors the pipeline's)."""
    return GeneratedCase(
        title=row.title,
        objective=row.objective,
        preconditions=row.preconditions or "",
        test_data=[
            TestDatum(name=key, value=str(value)) for key, value in (row.test_data or {}).items()
        ],
        steps=[TestStep.model_validate(step) for step in row.steps],
        expected_result=row.expected_result,
        priority=row.priority,  # type: ignore[arg-type]
        tags=list(row.tags),
        test_type=row.test_type,  # type: ignore[arg-type]
    )


__all__ = [
    "create_generation_request",
    "get_case",
    "get_request",
    "list_cases",
    "regenerate_case",
    "revalidate_case",
    "review_case",
]
