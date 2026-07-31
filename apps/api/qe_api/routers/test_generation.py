"""Test-generation routes — §16.3 L1623-1631, exactly the seven specified paths.

Two routers because the spec puts them under two prefixes: requests live under
``/test-generation``, review actions under ``/generated-tests``.

Every route carries a permission guard as a **dependency**, not only a check
inside the service. §26.2 L2100-2103 requires the check at the API-route level
*and* the service level, so both are present: the guard rejects before the
handler body runs, and the service's own ``principal.require`` protects it when
it is reached from the CLI or a test.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status

from qe_api.dependencies import SessionDep, require
from qe_api.schemas import (
    GeneratedTestCaseRead,
    Page,
    TestCaseReviewRequest,
    TestCaseValidationResponse,
    TestGenerationRequestCreate,
    TestGenerationRequestRead,
)
from qe_api.services import test_generation as service
from qe_api.services.support import DEFAULT_LIMIT, MAX_LIMIT
from qe_auth import Permission, Principal
from qe_common.test_generation import TestCaseStatus

router = APIRouter(prefix="/test-generation", tags=["test-generation"])
cases_router = APIRouter(prefix="/generated-tests", tags=["test-generation"])

ReaderDep = Annotated[Principal, Depends(require(Permission.TEST_GENERATION_READ))]
CreatorDep = Annotated[Principal, Depends(require(Permission.TEST_GENERATION_CREATE))]
ReviewerDep = Annotated[Principal, Depends(require(Permission.TEST_CASE_REVIEW))]
LimitDep = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
OffsetDep = Annotated[int, Query(ge=0)]

#: §26.8 L2190. Optional: a client that does not retry does not need one.
IdempotencyKeyDep = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        description="Replaying a POST with the same key returns the original request "
        "instead of billing a second generation.",
        max_length=255,
    ),
]


@router.post(
    "/requests",
    response_model=TestGenerationRequestRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create a generation request and enqueue its job",
)
async def create_request(
    payload: TestGenerationRequestCreate,
    session: SessionDep,
    principal: CreatorDep,
    response: Response,
    idempotency_key: IdempotencyKeyDep = None,
) -> TestGenerationRequestRead:
    """Accept the work and return the record to poll (§13.2).

    **202, never 200 with an inline result.** Generation involves several
    provider calls and is targeted at under 90 seconds (§30 L2378); holding the
    connection open for it would put a p99 measured in minutes on this endpoint.

    An unsupported configuration is refused here with 422 before any row exists
    (ADR-0212 Decision 2), and a repeated ``Idempotency-Key`` returns the
    original request rather than starting a second generation.
    """
    request, created = await service.create_generation_request(
        session,
        principal,
        project_id=payload.project_id,
        title=payload.title,
        source_type=payload.source_type,
        source_reference=payload.source_reference,
        framework=payload.framework,
        configuration=payload.configuration,
        repository_id=payload.repository_id,
        idempotency_key=idempotency_key,
    )
    if not created:
        # The work already exists; nothing new was accepted.
        response.status_code = status.HTTP_200_OK
    return TestGenerationRequestRead.from_row(request)


@router.get(
    "/requests/{request_id}",
    response_model=TestGenerationRequestRead,
    summary="Poll a generation request",
)
async def get_request(
    request_id: uuid.UUID, session: SessionDep, principal: ReaderDep
) -> TestGenerationRequestRead:
    """Read the authoritative row, including the four-entry prompt-version map."""
    return TestGenerationRequestRead.from_row(
        await service.get_request(session, principal, request_id)
    )


@router.get(
    "/requests/{request_id}/tests",
    response_model=Page[GeneratedTestCaseRead],
    summary="List the generated cases for a request",
)
async def list_request_tests(
    request_id: uuid.UUID,
    session: SessionDep,
    principal: ReaderDep,
    limit: LimitDep = DEFAULT_LIMIT,
    offset: OffsetDep = 0,
) -> Page[GeneratedTestCaseRead]:
    cases, total = await service.list_cases(
        session, principal, request_id, limit=limit, offset=offset
    )
    return Page(
        items=[GeneratedTestCaseRead.model_validate(case) for case in cases],
        total=total,
        limit=limit,
        offset=offset,
    )


@cases_router.post(
    "/{test_id}/approve",
    response_model=GeneratedTestCaseRead,
    summary="Approve one generated test",
)
async def approve_test(
    test_id: uuid.UUID,
    session: SessionDep,
    principal: ReviewerDep,
    payload: TestCaseReviewRequest | None = None,
) -> GeneratedTestCaseRead:
    """Nothing auto-approves — this route is the only way a case becomes APPROVED."""
    case = await service.review_case(
        session,
        principal,
        test_id,
        decision=TestCaseStatus.APPROVED,
        note=payload.note if payload else None,
    )
    return GeneratedTestCaseRead.model_validate(case)


@cases_router.post(
    "/{test_id}/reject",
    response_model=GeneratedTestCaseRead,
    summary="Reject one generated test",
)
async def reject_test(
    test_id: uuid.UUID,
    session: SessionDep,
    principal: ReviewerDep,
    payload: TestCaseReviewRequest | None = None,
) -> GeneratedTestCaseRead:
    case = await service.review_case(
        session,
        principal,
        test_id,
        decision=TestCaseStatus.REJECTED,
        note=payload.note if payload else None,
    )
    return GeneratedTestCaseRead.model_validate(case)


@cases_router.post(
    "/{test_id}/regenerate",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-run code generation for one test",
)
async def regenerate_test(
    test_id: uuid.UUID, session: SessionDep, principal: CreatorDep
) -> dict[str, str]:
    """Queue a **code-only** regeneration for this one case (ADR-0212 D3).

    Does not re-run decomposition, planning, or detailed generation, and does not
    touch any other case in the request — including its review state. It calls
    the provider, so it is asynchronous: 202 plus a job id to poll.
    """
    case, job = await service.regenerate_case(session, principal, test_id)
    return {"test_id": str(case.id), "request_id": str(case.request_id), "job_id": str(job.id)}


@cases_router.post(
    "/{test_id}/validate",
    response_model=TestCaseValidationResponse,
    summary="Re-run static validation on one test",
)
async def validate_test(
    test_id: uuid.UUID, session: SessionDep, principal: ReviewerDep
) -> TestCaseValidationResponse:
    """Re-run §22.2 levels 1-6 against the stored code.

    Synchronous — no provider call, so §13.1 applies. Nothing is executed:
    ``ast.parse`` builds a tree and stops (§23 L1991).
    """
    case = await service.revalidate_case(session, principal, test_id)
    return TestCaseValidationResponse(
        id=case.id,
        schema_valid=case.schema_valid,
        syntax_valid=case.syntax_valid,
        validation_status="PASSED" if case.schema_valid and case.syntax_valid else "FAILED",
        validation_errors=case.validation_errors,
    )


__all__ = ["cases_router", "router"]
