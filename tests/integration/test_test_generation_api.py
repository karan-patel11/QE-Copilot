"""N6 integration: the seven §16.3 routes, one test per ADR-0212 decision.

Each D-test is isolated and named after its decision, so a failure names the
decision that broke rather than "validation works" going red for an unrelated
reason.

The full-lifecycle test runs a **real Celery worker** against the real broker,
with only the provider substituted — ``MockProvider`` per ADR-0206, so the tier
stays deterministic and offline while everything else is genuine.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from celery.contrib.testing.worker import start_worker
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from qe_ai_gateway import MockProvider
from qe_ai_gateway.recorder import CommittingModelRunRecorder
from qe_auth import Role
from qe_common.jobs import JobState
from qe_common.test_generation import TestCaseStatus
from qe_database.models import (
    AuditLog,
    GeneratedTestCase,
    Job,
    ModelRun,
    Organisation,
    Project,
    PromptVersion,
    TestGenerationRequest,
)
from qe_database.session import get_engine
from qe_prompt_registry import seed_all
from qe_worker.celery_app import celery_app
from tests.helpers import UserFactory
from tests.helpers_testgen import REQUIREMENT, schema_aware_response

pytestmark = pytest.mark.integration

POLL_TIMEOUT_SECONDS = 30.0
POLL_INTERVAL_SECONDS = 0.1

BASE = "/api/v1/test-generation"
CASES = "/api/v1/generated-tests"


def _sync_session() -> Session:
    return Session(get_engine(), expire_on_commit=False)


@pytest.fixture()
def seeded_prompts(db: Session) -> Iterator[None]:
    """A freshly seeded registry, cleaned both before and after.

    ``prompt_versions`` has no ``organisation_id`` (ADR-0209 Decision 1), so it
    is global state that the per-tenant cascade does not reach. Cleaning on the
    way *in* as well as out means a test that deliberately corrupts a checksum
    (the drift test) cannot leave a poisoned registry for whatever runs next —
    and ``seed_all`` would not repair it, since an already-ACTIVE version is a
    no-op by design.
    """
    from sqlalchemy import delete

    db.execute(delete(PromptVersion))
    db.commit()
    seed_all(db)
    db.commit()
    yield
    db.execute(delete(PromptVersion))
    db.commit()


@pytest.fixture()
def project(db: Session, organisation: Organisation) -> Project:
    row = Project(
        organisation_id=organisation.id,
        name="Playback",
        slug=f"playback-{uuid.uuid4().hex[:8]}",
        description="",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture()
def mock_provider_worker(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A real worker whose only substitution is the provider (ADR-0206).

    ``start_worker`` runs the worker in-process, so patching the factory here
    reaches the code the worker actually executes. Everything else — broker,
    database, job state machine, pipeline, metering — is the real thing.
    """
    import qe_worker.tasks as tasks

    def _mock_provider() -> MockProvider:
        return MockProvider(
            responses=[schema_aware_response()],
            recorder=CommittingModelRunRecorder(_sync_session),
        )

    monkeypatch.setattr(tasks, "_build_provider", _mock_provider)
    celery_app.conf.update(broker_connection_retry_on_startup=True)
    with start_worker(celery_app, perform_ping_check=False, shutdown_timeout=30):
        yield None


def _payload(project: Project, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "project_id": str(project.id),
        "title": "Resume playback across devices",
        "source_reference": REQUIREMENT,
        "configuration": {},
    }
    body.update(overrides)
    return body


def _poll(client: TestClient, request_id: str, headers: dict[str, str]) -> dict[str, Any]:
    """Poll the request until terminal, collecting the states seen on the way."""
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    seen: list[str] = []
    while time.monotonic() < deadline:
        response = client.get(f"{BASE}/requests/{request_id}", headers=headers)
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        if not seen or seen[-1] != body["status"]:
            seen.append(body["status"])
        if body["status"] in {"COMPLETED", "FAILED", "PARTIALLY_COMPLETED", "TIMED_OUT"}:
            body["_states_seen"] = seen
            return body
        time.sleep(POLL_INTERVAL_SECONDS)
    raise AssertionError(f"request did not reach a terminal state; saw {seen}")


# ── D1 ──────────────────────────────────────────────────────────────────────


def test_d1_request_and_job_are_committed_in_one_transaction_before_dispatch(
    app_client: TestClient, db: Session, as_user: UserFactory, project: Project
) -> None:
    """Both rows durable, and the request carries the job id, on the 202 itself.

    Without this, ``CommittingModelRunRecorder``'s separate-connection writes
    would fail their foreign key with nothing going red (ADR-0212 Decision 1).
    """
    _, headers = as_user(Role.QUALITY_ENGINEER)
    response = app_client.post(f"{BASE}/requests", json=_payload(project), headers=headers)

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["job_id"] is not None

    # Queried on a *different* connection than the one the route used, so this
    # reads committed state rather than the route's session.
    request_row = db.execute(
        select(TestGenerationRequest).where(TestGenerationRequest.id == uuid.UUID(body["id"]))
    ).scalar_one()
    job_row = db.execute(select(Job).where(Job.id == uuid.UUID(body["job_id"]))).scalar_one()

    assert request_row.job_id == job_row.id
    assert job_row.payload["request_id"] == str(request_row.id)
    assert job_row.job_state is JobState.QUEUED
    assert request_row.job_state is JobState.QUEUED


def test_d1_metering_foreign_keys_resolve_because_the_rows_were_durable_first(
    app_client: TestClient,
    db: Session,
    as_user: UserFactory,
    project: Project,
    seeded_prompts: None,
    mock_provider_worker: None,
) -> None:
    """The ordering proof: ``model_runs`` rows exist, and they postdate the request.

    A ``model_runs`` row carrying this ``request_id`` can only exist if the
    request was committed before the worker's first provider call — the foreign
    key would have rejected it otherwise. The timestamp comparison shows the
    ordering directly rather than inferring it.
    """
    _, headers = as_user(Role.QUALITY_ENGINEER)
    created = app_client.post(f"{BASE}/requests", json=_payload(project), headers=headers).json()
    body = _poll(app_client, created["id"], headers)
    assert body["status"] == "COMPLETED", body

    request_id = uuid.UUID(created["id"])
    request_row = db.execute(
        select(TestGenerationRequest).where(TestGenerationRequest.id == request_id)
    ).scalar_one()
    job_row = db.execute(select(Job).where(Job.id == request_row.job_id)).scalar_one()
    first_run_at = db.scalar(
        select(func.min(ModelRun.created_at)).where(ModelRun.request_id == request_id)
    )
    run_count = db.scalar(
        select(func.count()).select_from(ModelRun).where(ModelRun.request_id == request_id)
    )

    assert run_count == 4, "every provider call should be metered against this request"
    assert first_run_at is not None
    assert request_row.created_at < first_run_at, "request must predate the first metering row"
    assert job_row.created_at < first_run_at, "job must predate the first metering row"


# ── D2 ──────────────────────────────────────────────────────────────────────


def test_d2_unsupported_config_rejected_before_job_creation(
    app_client: TestClient, db: Session, as_user: UserFactory, project: Project
) -> None:
    """422 at the boundary, and **nothing** written anywhere.

    Before ADR-0212 this fired in the worker, so a refused request had already
    become a row, a job, and a dispatched message.
    """
    _, headers = as_user(Role.QUALITY_ENGINEER)
    before_requests = db.scalar(select(func.count()).select_from(TestGenerationRequest))
    before_jobs = db.scalar(select(func.count()).select_from(Job))

    response = app_client.post(
        f"{BASE}/requests",
        json=_payload(project, configuration={"include_accessibility_cases": True}),
        headers=headers,
    )

    assert response.status_code == 422, response.text
    envelope = response.json()
    assert envelope["error"]["code"] == "TEST_CONFIG_UNSUPPORTED"
    assert "accessibility" in envelope["error"]["message"].lower()

    assert db.scalar(select(func.count()).select_from(TestGenerationRequest)) == before_requests
    assert db.scalar(select(func.count()).select_from(Job)) == before_jobs
    assert db.scalar(select(func.count()).select_from(ModelRun)) == 0


def test_d2_invalid_config_value_is_also_refused_at_the_boundary(
    app_client: TestClient, as_user: UserFactory, project: Project
) -> None:
    _, headers = as_user(Role.QUALITY_ENGINEER)
    response = app_client.post(
        f"{BASE}/requests",
        json=_payload(project, configuration={"number_of_tests": 99}),
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TEST_CONFIG_INVALID"


# ── D3 ──────────────────────────────────────────────────────────────────────


def test_d3_regenerate_reruns_codegen_only_and_attributes_to_the_original_request(
    app_client: TestClient,
    db: Session,
    as_user: UserFactory,
    project: Project,
    seeded_prompts: None,
    mock_provider_worker: None,
) -> None:
    """One provider call, one case touched, original ``request_id`` on the row."""
    _, headers = as_user(Role.QUALITY_ENGINEER)
    created = app_client.post(f"{BASE}/requests", json=_payload(project), headers=headers).json()
    _poll(app_client, created["id"], headers)
    request_id = uuid.UUID(created["id"])

    cases = app_client.get(f"{BASE}/requests/{request_id}/tests", headers=headers).json()["items"]
    target, other = cases[0], cases[1]
    other_status_before = other["human_status"]
    runs_before = (
        db.scalar(
            select(func.count()).select_from(ModelRun).where(ModelRun.request_id == request_id)
        )
        or 0
    )

    response = app_client.post(f"{CASES}/{target['id']}/regenerate", headers=headers)
    assert response.status_code == 202, response.text
    assert response.json()["request_id"] == str(request_id)

    job_id = uuid.UUID(response.json()["job_id"])
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        db.expire_all()
        job = db.execute(select(Job).where(Job.id == job_id)).scalar_one()
        if job.job_state is JobState.COMPLETED:
            break
        time.sleep(POLL_INTERVAL_SECONDS)
    else:
        raise AssertionError("regeneration job did not complete")

    runs_after = list(
        db.scalars(
            select(ModelRun).where(ModelRun.request_id == request_id).order_by(ModelRun.created_at)
        )
    )
    assert len(runs_after) == runs_before + 1, "exactly one further provider call"
    assert runs_after[-1].operation == "pytest_codegen", "codegen only — no other stage re-ran"
    assert runs_after[-1].request_id == request_id, "attributed to the original request"
    assert runs_after[-1].job_id == job_id, "but distinguishable by its own job"

    db.expire_all()
    untouched = db.execute(
        select(GeneratedTestCase).where(GeneratedTestCase.id == uuid.UUID(other["id"]))
    ).scalar_one()
    assert untouched.human_status == other_status_before, "other cases must not be disturbed"


# ── D4 ──────────────────────────────────────────────────────────────────────


def test_d4_response_returns_the_four_entry_prompt_version_map(
    app_client: TestClient,
    as_user: UserFactory,
    project: Project,
    seeded_prompts: None,
    mock_provider_worker: None,
) -> None:
    """The singular column is right about one stage in four, so it is not exposed."""
    _, headers = as_user(Role.QUALITY_ENGINEER)
    created = app_client.post(f"{BASE}/requests", json=_payload(project), headers=headers).json()
    body = _poll(app_client, created["id"], headers)

    assert body["prompt_versions"] == {
        "requirement_decomposition": "decompose-v1",
        "test_plan": "testplan-v1",
        "test_generation": "testgen-v1",
        "pytest_codegen": "pytest_codegen-v1",
    }
    assert "prompt_version" not in body, "the singular column must not be exposed"


def test_d4_prompt_versions_is_an_empty_map_before_any_stage_runs(
    app_client: TestClient, as_user: UserFactory, project: Project
) -> None:
    """Empty map, not null: "no stage has run" is distinguishable from "unknown"."""
    _, headers = as_user(Role.QUALITY_ENGINEER)
    created = app_client.post(f"{BASE}/requests", json=_payload(project), headers=headers).json()
    assert created["prompt_versions"] == {}


# ── D5 ──────────────────────────────────────────────────────────────────────


def test_d5_template_drift_surfaces_a_distinct_non_retryable_error_code(
    app_client: TestClient,
    db: Session,
    as_user: UserFactory,
    project: Project,
    seeded_prompts: None,
    mock_provider_worker: None,
) -> None:
    """Drift is raised in the worker, so it must reach the client as a code.

    Simulated by corrupting the stored checksum — exactly what editing a template
    without registering a new version produces. N7 branches on this code to
    render "contact engineering" rather than a retry button.
    """
    row = db.execute(
        select(PromptVersion).where(PromptVersion.version == "decompose-v1")
    ).scalar_one()
    row.template_checksum = "0" * 64
    db.commit()

    _, headers = as_user(Role.QUALITY_ENGINEER)
    created = app_client.post(f"{BASE}/requests", json=_payload(project), headers=headers).json()
    body = _poll(app_client, created["id"], headers)

    assert body["status"] == "FAILED"
    assert body["error_code"] == "PROMPT_TEMPLATE_DRIFT"
    assert body["error_code"] not in {"PROVIDER_ERROR", "PROVIDER_TIMEOUT", "INTERNAL_ERROR"}


# ── D6 ──────────────────────────────────────────────────────────────────────


def test_d6_unmet_kinds_reported_not_errored(
    app_client: TestClient,
    as_user: UserFactory,
    project: Project,
    seeded_prompts: None,
    mock_provider_worker: None,
) -> None:
    """A requested kind that no case carries is data, not a failure.

    The fixture asks for boundary and security cases; the canned response
    contains only positive and negative ones. The request must still complete.
    """
    _, headers = as_user(Role.QUALITY_ENGINEER)
    created = app_client.post(
        f"{BASE}/requests",
        json=_payload(
            project,
            configuration={"include_boundary_cases": True, "include_security_cases": True},
        ),
        headers=headers,
    ).json()
    body = _poll(app_client, created["id"], headers)

    assert body["status"] == "COMPLETED", "an unmet kind must not fail the request"
    assert set(body["unmet_requested_kinds"]) == {"boundary", "security"}
    assert body["produced_by_type"] == {"positive": 1, "negative": 1}
    assert body["case_count"] == 2, "nothing was synthesised to fill the empty buckets"
    assert body["coverage_notes"]


# ── Idempotency (§26.8 L2190) ───────────────────────────────────────────────


def test_idempotency_key_replay_returns_the_original_without_billing_again(
    app_client: TestClient, db: Session, as_user: UserFactory, project: Project
) -> None:
    _, headers = as_user(Role.QUALITY_ENGINEER)
    keyed = {**headers, "Idempotency-Key": f"key-{uuid.uuid4().hex}"}

    first = app_client.post(f"{BASE}/requests", json=_payload(project), headers=keyed)
    second = app_client.post(f"{BASE}/requests", json=_payload(project), headers=keyed)

    assert first.status_code == 202
    assert second.status_code == 200, "a replay accepts nothing new"
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["job_id"] == second.json()["job_id"]

    total = db.scalar(
        select(func.count())
        .select_from(TestGenerationRequest)
        .where(TestGenerationRequest.id == uuid.UUID(first.json()["id"]))
    )
    assert total == 1


# ── Review actions and audit (§12.2, §26.8) ─────────────────────────────────


def test_approve_and_reject_are_audited_with_before_and_after_state(
    app_client: TestClient,
    db: Session,
    as_user: UserFactory,
    project: Project,
    seeded_prompts: None,
    mock_provider_worker: None,
) -> None:
    user, headers = as_user(Role.QUALITY_ENGINEER)
    created = app_client.post(f"{BASE}/requests", json=_payload(project), headers=headers).json()
    _poll(app_client, created["id"], headers)
    cases = app_client.get(f"{BASE}/requests/{created['id']}/tests", headers=headers).json()[
        "items"
    ]

    approved = app_client.post(f"{CASES}/{cases[0]['id']}/approve", headers=headers)
    assert approved.status_code == 200
    assert approved.json()["human_status"] == TestCaseStatus.APPROVED.value
    assert approved.json()["reviewed_by"] == str(user.id)

    rejected = app_client.post(
        f"{CASES}/{cases[1]['id']}/reject",
        json={"note": "duplicates an existing suite"},
        headers=headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["human_status"] == TestCaseStatus.REJECTED.value

    entries = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type == "generated_test_case")
            .order_by(AuditLog.created_at)
        )
    )
    assert len(entries) >= 2
    changes = entries[-2].changes or {}
    assert changes["human_status"] == {"before": "PENDING_REVIEW", "after": "APPROVED"}
    assert entries[-1].actor_user_id == user.id


def test_nothing_auto_approves(
    app_client: TestClient,
    as_user: UserFactory,
    project: Project,
    seeded_prompts: None,
    mock_provider_worker: None,
) -> None:
    """§8.2, §11.5 L890 — every case lands pending, always."""
    _, headers = as_user(Role.QUALITY_ENGINEER)
    created = app_client.post(f"{BASE}/requests", json=_payload(project), headers=headers).json()
    _poll(app_client, created["id"], headers)
    cases = app_client.get(f"{BASE}/requests/{created['id']}/tests", headers=headers).json()[
        "items"
    ]
    assert cases, "the fixture should produce cases"
    assert all(case["human_status"] == "PENDING_REVIEW" for case in cases)


def test_validate_reruns_the_static_chain_without_executing_anything(
    app_client: TestClient,
    db: Session,
    as_user: UserFactory,
    project: Project,
    seeded_prompts: None,
    mock_provider_worker: None,
) -> None:
    _, headers = as_user(Role.QUALITY_ENGINEER)
    created = app_client.post(f"{BASE}/requests", json=_payload(project), headers=headers).json()
    _poll(app_client, created["id"], headers)
    case_id = app_client.get(f"{BASE}/requests/{created['id']}/tests", headers=headers).json()[
        "items"
    ][0]["id"]

    # Corrupt the stored code, then re-validate: the chain must notice.
    row = db.execute(
        select(GeneratedTestCase).where(GeneratedTestCase.id == uuid.UUID(case_id))
    ).scalar_one()
    row.generated_code = "def test_x(:\n    pass\n"
    db.commit()

    response = app_client.post(f"{CASES}/{case_id}/validate", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["validation_status"] == "FAILED"
    assert body["syntax_valid"] is False
    assert any(error["check"] == "syntax" for error in body["validation_errors"])


# ── Full lifecycle ──────────────────────────────────────────────────────────


def test_full_lifecycle_post_to_completed_with_populated_summary(
    app_client: TestClient,
    db: Session,
    as_user: UserFactory,
    project: Project,
    seeded_prompts: None,
    mock_provider_worker: None,
) -> None:
    """POST → real worker claims → COMPLETED → GET returns the populated summary."""
    _, headers = as_user(Role.QUALITY_ENGINEER)
    response = app_client.post(f"{BASE}/requests", json=_payload(project), headers=headers)
    assert response.status_code == 202
    created = response.json()

    body = _poll(app_client, created["id"], headers)

    assert body["status"] == "COMPLETED"
    assert body["case_count"] == 2
    assert body["validation_passed"] == 2
    assert body["validation_failed"] == 0
    assert len(body["model_run_ids"]) == 4
    assert body["prompt_versions"]["pytest_codegen"] == "pytest_codegen-v1"
    # QUEUED is the state the API writes; the worker owns everything after it.
    assert body["_states_seen"][0] == "QUEUED"
    assert body["_states_seen"][-1] == "COMPLETED"

    job = db.execute(select(Job).where(Job.id == uuid.UUID(created["job_id"]))).scalar_one()
    assert job.job_state is JobState.COMPLETED
    assert job.started_at is not None and job.finished_at is not None

    cases = app_client.get(f"{BASE}/requests/{created['id']}/tests", headers=headers).json()
    assert cases["total"] == 2
    assert cases["items"][0]["execution_status"] is None, "sandbox is P1 — never executed"
