"""N5 integration: seeding, the full pipeline, and metering durability.

Requires live Postgres. These are the assertions that cannot be made against a
fake — lifecycle rows actually written, and a transaction actually rolled back.

The sharpest test here is :func:`test_model_runs_survive_a_rollback_of_the_pipeline`:
it is the direct proof of ADR-0211 Decision 2, and it fails if anyone ever
switches N5 back to the flushing recorder.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from qe_ai_gateway import MockProvider
from qe_ai_gateway.recorder import CommittingModelRunRecorder
from qe_common.jobs import JobState
from qe_common.prompts import PromptStatus
from qe_common.test_generation import SourceType, TestCaseStatus, TestFramework
from qe_database.models import (
    GeneratedTestCase,
    ModelRun,
    Organisation,
    Project,
    PromptVersion,
    TestGenerationRequest,
)
from qe_database.session import get_engine
from qe_prompt_registry import get_active, seed_all
from qe_test_generation import run_generation
from qe_test_generation.config import validate_configuration
from tests.helpers_testgen import REQUIREMENT, STAGE_RESPONSES

pytestmark = pytest.mark.integration


def _session() -> Session:
    return Session(get_engine(), expire_on_commit=False)


@pytest.fixture()
def seeded_prompts(db: Session) -> Iterator[None]:
    """A registry seeded through the full lifecycle, torn down afterwards.

    ``prompt_versions`` has no ``organisation_id`` (ADR-0209 Decision 1), so it is
    not covered by the tenant cascade every other fixture relies on and must be
    cleaned up explicitly.
    """
    seed_all(db)
    db.commit()
    yield
    db.execute(delete(PromptVersion))
    db.commit()


@pytest.fixture()
def request_row(db: Session, organisation: Organisation) -> TestGenerationRequest:
    """A committed request, as ADR-0204's flow guarantees before dispatch."""
    project = Project(
        organisation_id=organisation.id, name="Playback", slug="playback", description=""
    )
    db.add(project)
    db.flush()

    row = TestGenerationRequest(
        organisation_id=organisation.id,
        project_id=project.id,
        title="Resume playback across devices",
        source_type=SourceType.REQUIREMENT_TEXT.value,
        source_reference=REQUIREMENT,
        framework=TestFramework.PYTEST.value,
        status=JobState.QUEUED.value,
        configuration=validate_configuration({}).model_dump(mode="json"),
    )
    db.add(row)
    db.commit()
    return row


def _provider() -> MockProvider:
    """MockProvider metering through the committing recorder, as the worker wires it."""
    return MockProvider(
        responses=STAGE_RESPONSES,
        recorder=CommittingModelRunRecorder(_session),
    )


# --- Seeding walks the lifecycle -------------------------------------------


def test_seeding_reaches_active_through_all_five_transitions(db: Session) -> None:
    """No shortcut insert: ADR-0211 Decision 3.

    Asserted on the recorded outcome rather than on the final status alone,
    because a raw ``INSERT ... status='ACTIVE'`` would also end at ACTIVE.
    """
    db.execute(delete(PromptVersion))
    db.commit()

    outcomes = seed_all(db)
    db.commit()

    assert len(outcomes) == 4
    for outcome in outcomes:
        assert outcome.action == "created"
        assert outcome.transitions == 5, "DRAFT to ACTIVE is five forward steps"
        assert outcome.final_status is PromptStatus.ACTIVE

    for name in ("decompose", "testplan", "testgen", "pytest_codegen"):
        assert get_active(db, name).status == PromptStatus.ACTIVE.value

    db.execute(delete(PromptVersion))
    db.commit()


def test_seeding_is_idempotent(db: Session, seeded_prompts: None) -> None:
    """Safe on every deploy: the second run changes nothing."""
    outcomes = seed_all(db)
    db.commit()

    assert all(o.action == "already_active" for o in outcomes)
    assert all(o.transitions == 0 for o in outcomes)
    assert db.scalar(select(func.count()).select_from(PromptVersion)) == 4


def test_at_most_one_active_version_per_prompt(db: Session, seeded_prompts: None) -> None:
    """The database guarantee behind ``get_active`` returning exactly one row."""
    counts = db.execute(
        select(PromptVersion.prompt_name, func.count())
        .where(PromptVersion.status == PromptStatus.ACTIVE.value)
        .group_by(PromptVersion.prompt_name)
    ).all()
    assert {row[0]: row[1] for row in counts} == {
        "decompose": 1,
        "testplan": 1,
        "testgen": 1,
        "pytest_codegen": 1,
    }


# --- The full pipeline ------------------------------------------------------


def test_full_pipeline_persists_cases_and_meters_every_call(
    db: Session, seeded_prompts: None, request_row: TestGenerationRequest
) -> None:
    outcome = run_generation(_session, request_row.id, provider=_provider())

    assert outcome.state is JobState.COMPLETED
    assert outcome.case_count == 2

    cases = list(
        db.scalars(
            select(GeneratedTestCase)
            .where(GeneratedTestCase.request_id == request_row.id)
            .order_by(GeneratedTestCase.ordinal)
        )
    )
    assert len(cases) == 2
    for case in cases:
        # Nothing auto-approves (§8.2, §11.5 L890).
        assert case.human_status == TestCaseStatus.PENDING_REVIEW.value
        # The sandbox is P1; NULL is the honest "not executed" (ADR-0205).
        assert case.execution_status is None
        assert case.schema_valid and case.syntax_valid
        assert case.framework == TestFramework.PYTEST.value

    runs = list(db.scalars(select(ModelRun).where(ModelRun.request_id == request_row.id)))
    assert len(runs) == 4
    assert {run.operation for run in runs} == {
        "requirement_decomposition",
        "test_plan",
        "test_generation",
        "pytest_codegen",
    }
    assert all(run.status == "SUCCEEDED" for run in runs)


def test_summary_traces_cases_back_to_their_model_runs(
    db: Session, seeded_prompts: None, request_row: TestGenerationRequest
) -> None:
    """Decomposition is not persisted, so the summary carries the provenance."""
    run_generation(_session, request_row.id, provider=_provider())
    db.refresh(request_row)

    summary: dict[str, Any] = request_row.summary or {}
    run_ids = {
        str(r.id) for r in db.scalars(select(ModelRun).where(ModelRun.request_id == request_row.id))
    }

    assert set(summary["model_run_ids"]) == run_ids
    assert summary["decomposition_cardinalities"]["actors"] == 1
    assert summary["prompt_versions"]["requirement_decomposition"] == "decompose-v1"
    assert REQUIREMENT not in str(summary), "summary must not duplicate requirement text"


# --- ADR-0211 Decision 2: the durability proof ------------------------------


def test_model_runs_survive_a_rollback_of_the_pipeline(
    db: Session,
    seeded_prompts: None,
    request_row: TestGenerationRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A late failure rolls back the cases and leaves the metering intact.

    This is the whole point of Decision 2. The four provider calls happened and
    were billed; a failure in persistence must not erase the record of them.
    Asserted by querying the database directly, not by reading application logs.
    """
    import qe_test_generation.pipeline as pipeline

    def _explode(**_: object) -> dict[str, Any]:
        raise RuntimeError("late pipeline failure, after every provider call")

    monkeypatch.setattr(pipeline, "build_summary", _explode)

    with pytest.raises(RuntimeError, match="late pipeline failure"):
        run_generation(_session, request_row.id, provider=_provider())

    cases = db.scalar(
        select(func.count())
        .select_from(GeneratedTestCase)
        .where(GeneratedTestCase.request_id == request_row.id)
    )
    runs = db.scalar(
        select(func.count()).select_from(ModelRun).where(ModelRun.request_id == request_row.id)
    )

    assert cases == 0, "the persistence transaction must have rolled back"
    assert runs == 4, (
        "model_runs rows for calls that were already billed must survive the rollback "
        "(ADR-0211 Decision 2) — if this is 0, N5 is back on the flushing recorder"
    )

    db.refresh(request_row)
    assert request_row.job_state is JobState.FAILED
    assert request_row.error and "late pipeline failure" in request_row.error


def test_a_provider_failure_mid_pipeline_keeps_earlier_rows(
    db: Session, seeded_prompts: None, request_row: TestGenerationRequest
) -> None:
    """Same durability, triggered by the provider rather than by persistence."""
    from qe_common.errors import ProviderError

    provider = MockProvider(
        responses=STAGE_RESPONSES,
        failures={3: ProviderError("provider exploded")},
        recorder=CommittingModelRunRecorder(_session),
    )

    with pytest.raises(ProviderError):
        run_generation(_session, request_row.id, provider=provider)

    runs = list(db.scalars(select(ModelRun).where(ModelRun.request_id == request_row.id)))
    assert len(runs) == 3
    assert [r.status for r in runs[:2]] == ["SUCCEEDED", "SUCCEEDED"]
    assert runs[2].status == "FAILED"

    db.refresh(request_row)
    assert request_row.job_state is JobState.FAILED


def test_an_unseeded_registry_fails_before_any_provider_call(
    db: Session, request_row: TestGenerationRequest
) -> None:
    """Pre-flight resolution means an unseeded environment costs nothing."""
    from qe_common.errors import PromptVersionNotFoundError

    db.execute(delete(PromptVersion))
    db.commit()

    provider = MockProvider(
        responses=STAGE_RESPONSES, recorder=CommittingModelRunRecorder(_session)
    )
    with pytest.raises(PromptVersionNotFoundError):
        run_generation(_session, request_row.id, provider=provider)

    assert provider.call_count == 0
    assert (
        db.scalar(
            select(func.count()).select_from(ModelRun).where(ModelRun.request_id == request_row.id)
        )
        == 0
    )


def test_accessibility_request_is_refused_before_any_provider_call(
    db: Session, seeded_prompts: None, organisation: Organisation
) -> None:
    """ADR-0208's 422, asserted through the service rather than a code-path grep."""
    from qe_common.errors import TestConfigUnsupportedError

    project = Project(organisation_id=organisation.id, name="A11y", slug="a11y", description="")
    db.add(project)
    db.flush()
    row = TestGenerationRequest(
        organisation_id=organisation.id,
        project_id=project.id,
        title="Accessibility",
        source_type=SourceType.REQUIREMENT_TEXT.value,
        source_reference=REQUIREMENT,
        framework=TestFramework.PYTEST.value,
        status=JobState.QUEUED.value,
        # Stored as submitted, so the refusal path sees a realistic row.
        configuration={
            **validate_configuration({}).model_dump(mode="json"),
            "include_accessibility_cases": True,
        },
    )
    db.add(row)
    db.commit()

    provider = MockProvider(
        responses=STAGE_RESPONSES, recorder=CommittingModelRunRecorder(_session)
    )
    with pytest.raises(TestConfigUnsupportedError) as exc:
        run_generation(_session, row.id, provider=provider)

    assert exc.value.http_status == 422
    assert provider.call_count == 0
    assert (
        db.scalar(select(func.count()).select_from(ModelRun).where(ModelRun.request_id == row.id))
        == 0
    )


def test_duplicate_cases_are_linked_by_row_id(
    db: Session, seeded_prompts: None, request_row: TestGenerationRequest
) -> None:
    """``duplicate_of`` resolves to the earlier row, not to an ordinal."""
    import copy as _copy

    responses = _copy.deepcopy(STAGE_RESPONSES)
    responses[2]["cases"][1] = _copy.deepcopy(responses[2]["cases"][0])
    responses[3]["items"][1]["title"] = responses[3]["items"][0]["title"]

    provider = MockProvider(responses=responses, recorder=CommittingModelRunRecorder(_session))
    run_generation(_session, request_row.id, provider=provider)

    cases = list(
        db.scalars(
            select(GeneratedTestCase)
            .where(GeneratedTestCase.request_id == request_row.id)
            .order_by(GeneratedTestCase.ordinal)
        )
    )
    assert cases[0].duplicate_of is None
    assert cases[1].duplicate_of == cases[0].id
    assert cases[1].duplicate_score is not None and cases[1].duplicate_score >= 0.85
    # A duplicate is still a valid test.
    assert cases[1].schema_valid and cases[1].syntax_valid


def test_generated_rows_populate_every_required_column(
    db: Session, seeded_prompts: None, request_row: TestGenerationRequest
) -> None:
    """No unexplained NULLs in the 27-column row (§15.6 + ADR-0203 additions)."""
    run_generation(_session, request_row.id, provider=_provider())

    case = db.scalar(
        select(GeneratedTestCase).where(GeneratedTestCase.request_id == request_row.id)
    )
    assert case is not None
    for column in GeneratedTestCase.__table__.columns:
        value = getattr(case, column.name)
        if column.nullable:
            continue
        assert value is not None, f"non-nullable column {column.name} is NULL"

    # The three legitimately-NULL columns, each for a recorded reason.
    assert case.execution_status is None  # sandbox is P1 (ADR-0205)
    assert case.reviewed_by is None and case.reviewed_at is None  # not yet reviewed
