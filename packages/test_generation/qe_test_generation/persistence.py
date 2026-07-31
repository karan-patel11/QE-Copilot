"""Mapping validated cases onto ``generated_test_cases`` (§15.6, ADR-0203).

A mapping, not a translation: :class:`~qe_test_generation.contracts.GeneratedCase`
was named to track the table, so this module mostly moves values across and
records what validation found.

**Adds no columns.** Every field written here already exists in migration `0005`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from qe_common.test_generation import TestCaseStatus, TestType
from qe_database.models import GeneratedTestCase, TestGenerationRequest
from qe_test_generation.config import TestGeneratorConfig
from qe_test_generation.contracts import (
    Decomposition,
    GeneratedCase,
    TestPlan,
    decomposition_summary,
)
from qe_test_generation.validation import CaseValidation


def persist_cases(
    session: Session,
    *,
    request: TestGenerationRequest,
    cases: Sequence[GeneratedCase],
    codes: Sequence[str],
    validations: Sequence[CaseValidation],
) -> list[GeneratedTestCase]:
    """Write one row per case, in order, resolving duplicate references as it goes.

    Rows are flushed one at a time because ``duplicate_of`` points at another row
    in this same batch: the counterpart's id does not exist until its insert has
    been flushed. Cases are validated in order and can only duplicate an
    *earlier* case, so a single forward pass always has the id it needs.

    Failing cases are persisted with their reasons rather than dropped (ADR-0205,
    §22.2 L1985) — dropping them would hide model failure modes and leave the
    reviewer guessing at what was attempted.
    """
    rows: list[GeneratedTestCase] = []
    id_by_ordinal: dict[int, uuid.UUID] = {}

    for ordinal, (case, code, validation) in enumerate(zip(cases, codes, validations, strict=True)):
        duplicate_of = (
            id_by_ordinal.get(validation.duplicate_of_ordinal)
            if validation.duplicate_of_ordinal is not None
            else None
        )
        row = GeneratedTestCase(
            request_id=request.id,
            organisation_id=request.organisation_id,
            ordinal=ordinal,
            title=case.title,
            objective=case.objective,
            preconditions=case.preconditions or None,
            # Collapsed from the wire's list-of-pairs back into the JSONB map the
            # column holds; the list shape exists only to satisfy strict decoding.
            test_data={datum.name: datum.value for datum in case.test_data},
            steps=[step.model_dump() for step in case.steps],
            expected_result=case.expected_result,
            priority=case.priority.value,
            tags=list(case.tags),
            test_type=case.test_type.value,
            framework=request.framework,
            generated_code=code,
            schema_valid=validation.schema_valid,
            syntax_valid=validation.syntax_valid,
            validation_errors=[finding.as_dict() for finding in validation.findings],
            # Stays NULL: nothing executes generated code in this phase, and the
            # sandbox that would populate it is P1 (ADR-0205, §39 L2910).
            execution_status=None,
            # Nothing auto-approves — §8.2, §11.5 L890, ADR-0203.
            human_status=TestCaseStatus.PENDING_REVIEW.value,
            duplicate_of=duplicate_of,
            duplicate_score=validation.duplicate_score,
        )
        session.add(row)
        session.flush()
        id_by_ordinal[ordinal] = row.id
        rows.append(row)

    return rows


def build_summary(
    *,
    config: TestGeneratorConfig,
    decomposition: Decomposition,
    plan: TestPlan,
    cases: Sequence[GeneratedCase],
    validations: Sequence[CaseValidation],
    prompt_versions: dict[str, str],
    model_run_ids: Sequence[uuid.UUID | None],
) -> dict[str, Any]:
    """The per-request ``summary`` JSONB: what was asked for, what came back.

    Carries the traceability that decomposition's non-persistence would otherwise
    cost (ADR-0207): the ``model_runs`` ids of all four calls, and the *shape* of
    the decomposition as field cardinalities. No decomposition content — the
    requirement is untrusted and potentially sensitive, and copying it here would
    recreate the second copy ADR-0207 declined to create.
    """
    produced: dict[str, int] = {}
    for case in cases:
        produced[case.test_type.value] = produced.get(case.test_type.value, 0) + 1

    # ADR-0208: the include_* flags are requests, not guarantees. A gap is
    # reported rather than filled with a fabricated case — a requirement with no
    # failure conditions legitimately yields no negative cases.
    unmet = [
        kind.value
        for kind, requested in config.requested_kinds.items()
        if requested and not produced.get(kind.value)
    ]

    failed = [
        index for index, v in enumerate(validations) if not (v.schema_valid and v.syntax_valid)
    ]
    duplicates = [index for index, v in enumerate(validations) if v.is_duplicate]

    return {
        "case_count": len(cases),
        "requested_count": config.number_of_tests,
        "produced_by_type": produced,
        "unmet_requested_kinds": unmet,
        "coverage_notes": plan.coverage_notes,
        "validation": {
            "passed": len(cases) - len(failed),
            "failed": len(failed),
            "failed_ordinals": failed,
            "duplicate_ordinals": duplicates,
        },
        "prompt_versions": prompt_versions,
        "model_run_ids": [str(run_id) for run_id in model_run_ids if run_id is not None],
        "decomposition_cardinalities": decomposition_summary(decomposition),
    }


def unmet_kinds(config: TestGeneratorConfig, cases: Sequence[GeneratedCase]) -> list[TestType]:
    """Requested case kinds that no generated case carries."""
    produced = {case.test_type for case in cases}
    return [
        kind
        for kind, requested in config.requested_kinds.items()
        if requested and kind not in produced
    ]


__all__ = ["build_summary", "persist_cases", "unmet_kinds"]
