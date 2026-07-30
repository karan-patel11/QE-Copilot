"""T5 PASS: create a job via the API, let a real worker run it, poll until COMPLETED.

A genuine Celery worker consuming from the Redis broker runs alongside the test,
so this exercises the whole path — HTTP → database → broker → worker → database
→ polling — with nothing mocked.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator

import pytest
from celery.contrib.testing.worker import start_worker
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from qe_auth import Role
from qe_common.jobs import JobState
from qe_database.models import Job, Organisation, Project
from qe_worker.celery_app import celery_app
from tests.helpers import UserFactory

pytestmark = pytest.mark.integration

POLL_TIMEOUT_SECONDS = 30.0
POLL_INTERVAL_SECONDS = 0.1


@pytest.fixture(scope="module")
def worker() -> Iterator[None]:
    """A real Celery worker consuming ``qe_worker.run_job`` from Redis."""
    # Importing registers run_job on the shared app before the worker starts.
    import qe_worker.tasks  # noqa: F401

    celery_app.conf.update(broker_connection_retry_on_startup=True)
    with start_worker(celery_app, perform_ping_check=False, shutdown_timeout=30):
        yield None


def _poll_until_terminal(
    client: TestClient, job_id: str, headers: dict[str, str]
) -> dict[str, object]:
    """Poll the status endpoint the way a real client would."""
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    body: dict[str, object] = {}
    while time.monotonic() < deadline:
        resp = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body["state"] in {
            JobState.COMPLETED.value,
            JobState.FAILED.value,
            JobState.CANCELLED.value,
            JobState.TIMED_OUT.value,
            JobState.PARTIALLY_COMPLETED.value,
        }:
            return body
        time.sleep(POLL_INTERVAL_SECONDS)
    raise AssertionError(
        f"job did not reach a terminal state within {POLL_TIMEOUT_SECONDS}s: {body}"
    )


def test_a_job_created_via_the_api_is_run_by_the_worker_and_polls_completed(
    app_client: TestClient, db: Session, as_user: UserFactory, worker: None
) -> None:
    """The headline assertion for the job framework."""
    _, engineer = as_user(Role.ENGINEER)

    created = app_client.post(
        "/api/v1/jobs",
        headers=engineer,
        json={"kind": "health_check", "payload": {"note": "t5"}},
    )
    assert created.status_code == 202, created.text
    body = created.json()
    job_id = body["id"]
    assert body["state"] == JobState.QUEUED.value
    assert body["queued_at"] is not None
    assert body["payload"] == {"note": "t5"}

    polled = _poll_until_terminal(app_client, job_id, engineer)

    assert polled["state"] == JobState.COMPLETED.value, polled
    assert polled["attempts"] == 1
    assert polled["started_at"] is not None
    assert polled["finished_at"] is not None
    assert polled["error"] is None
    result = polled["result"]
    assert isinstance(result, dict)
    assert result["ok"] is True
    assert result["echo"] == {"note": "t5"}

    # The transitions were persisted, not just reported over HTTP.
    row = db.execute(select(Job).where(Job.id == uuid.UUID(job_id))).scalar_one()
    db.refresh(row)
    assert row.state == JobState.COMPLETED.value
    assert row.celery_task_id
    assert row.attempts == 1
    assert row.queued_at is not None and row.started_at is not None
    assert row.started_at >= row.queued_at
    assert row.finished_at is not None and row.finished_at >= row.started_at


def test_a_job_can_be_attached_to_a_project(
    app_client: TestClient,
    db: Session,
    as_user: UserFactory,
    organisation: Organisation,
    worker: None,
) -> None:
    project = Project(
        organisation_id=organisation.id, name="Jobs", slug=f"jobs-{uuid.uuid4().hex[:8]}"
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    _, engineer = as_user(Role.ENGINEER)

    created = app_client.post(
        "/api/v1/jobs",
        headers=engineer,
        json={"kind": "health_check", "project_id": str(project.id)},
    )

    assert created.status_code == 202, created.text
    assert created.json()["project_id"] == str(project.id)
    polled = _poll_until_terminal(app_client, created.json()["id"], engineer)
    assert polled["state"] == JobState.COMPLETED.value

    filtered = app_client.get(f"/api/v1/jobs?project_id={project.id}", headers=engineer).json()
    assert [item["id"] for item in filtered["items"]] == [created.json()["id"]]


def test_a_redelivered_message_does_not_run_the_job_twice(
    app_client: TestClient, db: Session, as_user: UserFactory, worker: None
) -> None:
    """The claim is idempotent: only a QUEUED job can be taken."""
    from qe_worker.tasks import run_job

    _, engineer = as_user(Role.ENGINEER)
    created = app_client.post("/api/v1/jobs", headers=engineer, json={"kind": "health_check"})
    job_id = created.json()["id"]
    assert _poll_until_terminal(app_client, job_id, engineer)["state"] == JobState.COMPLETED.value

    replay = run_job.delay(job_id).get(timeout=30)

    assert replay["claimed"] is False
    row = db.execute(select(Job).where(Job.id == uuid.UUID(job_id))).scalar_one()
    db.refresh(row)
    assert row.attempts == 1, "the job ran exactly once"


def test_an_unknown_job_id_is_ignored_by_the_worker(worker: None) -> None:
    from qe_worker.tasks import run_job

    outcome = run_job.delay(str(uuid.uuid4())).get(timeout=30)

    assert outcome == {"job_id": outcome["job_id"], "state": None, "claimed": False}


def test_polling_another_tenants_job_is_404(
    app_client: TestClient, db: Session, as_user: UserFactory, other_organisation: Organisation
) -> None:
    foreign = Job(
        organisation_id=other_organisation.id,
        kind="health_check",
        state=JobState.COMPLETED.value,
        payload={},
    )
    db.add(foreign)
    db.commit()
    db.refresh(foreign)
    _, engineer = as_user(Role.ENGINEER)

    resp = app_client.get(f"/api/v1/jobs/{foreign.id}", headers=engineer)

    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "JOB_NOT_FOUND"
    listed = app_client.get("/api/v1/jobs", headers=engineer).json()
    assert str(foreign.id) not in [item["id"] for item in listed["items"]]


def test_creating_a_job_on_another_tenants_project_is_404(
    app_client: TestClient, db: Session, as_user: UserFactory, other_organisation: Organisation
) -> None:
    foreign_project = Project(
        organisation_id=other_organisation.id,
        name="Theirs",
        slug=f"theirs-{uuid.uuid4().hex[:8]}",
    )
    db.add(foreign_project)
    db.commit()
    db.refresh(foreign_project)
    _, engineer = as_user(Role.ENGINEER)

    resp = app_client.post(
        "/api/v1/jobs",
        headers=engineer,
        json={"kind": "health_check", "project_id": str(foreign_project.id)},
    )

    assert resp.status_code == 404, resp.text
    assert db.execute(select(Job).where(Job.project_id == foreign_project.id)).first() is None


def test_an_unknown_job_kind_is_rejected_before_anything_is_queued(
    app_client: TestClient, as_user: UserFactory
) -> None:
    _, engineer = as_user(Role.ENGINEER)

    resp = app_client.post("/api/v1/jobs", headers=engineer, json={"kind": "mine_bitcoin"})

    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_job_routes_require_authentication(app_client: TestClient) -> None:
    assert app_client.get("/api/v1/jobs").status_code == 401
    assert app_client.post("/api/v1/jobs", json={"kind": "health_check"}).status_code == 401
    assert app_client.get(f"/api/v1/jobs/{uuid.uuid4()}").status_code == 401


def test_jobs_are_listed_newest_first_and_filterable_by_state(
    app_client: TestClient, as_user: UserFactory, worker: None
) -> None:
    _, engineer = as_user(Role.ENGINEER)
    ids = []
    for index in range(2):
        created = app_client.post(
            "/api/v1/jobs",
            headers=engineer,
            json={"kind": "health_check", "payload": {"index": index}},
        )
        assert created.status_code == 202, created.text
        ids.append(created.json()["id"])
        _poll_until_terminal(app_client, created.json()["id"], engineer)

    listed = app_client.get("/api/v1/jobs", headers=engineer).json()
    assert [item["id"] for item in listed["items"]] == list(reversed(ids))
    assert listed["total"] == 2

    completed = app_client.get("/api/v1/jobs?state=COMPLETED", headers=engineer).json()
    assert completed["total"] == 2
    running = app_client.get("/api/v1/jobs?state=RUNNING", headers=engineer).json()
    assert running["total"] == 0
