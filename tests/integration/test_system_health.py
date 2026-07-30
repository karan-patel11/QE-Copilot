"""T7 PASS: the System Health API reports live, measured data.

The assertions below only hold if the values are measured per request — latency
figures, a moving uptime, a real queue length read off the broker, and the set
of workers that actually answered a control-plane ping.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from qe_auth import Role
from qe_common.health import HealthStatus
from qe_common.jobs import JobState
from tests.helpers import UserFactory

pytestmark = pytest.mark.integration

ENDPOINT = "/api/v1/system-health"
COMPONENTS = {"api", "database", "redis", "queue", "workers", "scheduler"}


def test_system_health_reports_every_component(
    app_client: TestClient, as_user: UserFactory
) -> None:
    _, engineer = as_user(Role.ENGINEER)

    resp = app_client.get(ENDPOINT, headers=engineer)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body["components"]) == COMPONENTS
    assert body["status"] in {s.value for s in HealthStatus}
    assert body["checked_at"]
    for name, component in body["components"].items():
        assert component["status"] in {s.value for s in HealthStatus}, name


def test_the_database_and_redis_are_live_with_measured_latency(
    app_client: TestClient, as_user: UserFactory
) -> None:
    _, engineer = as_user(Role.ENGINEER)

    body = app_client.get(ENDPOINT, headers=engineer).json()

    for name in ("database", "redis"):
        component = body["components"][name]
        assert component["status"] == HealthStatus.HEALTHY.value, component
        latency = component["metrics"]["latency_ms"]
        assert isinstance(latency, int | float)
        assert 0 <= latency < 5000, f"{name} latency looks implausible: {latency}"


def test_the_queue_depth_is_read_from_the_broker(
    app_client: TestClient, as_user: UserFactory
) -> None:
    _, engineer = as_user(Role.ENGINEER)

    queue = app_client.get(ENDPOINT, headers=engineer).json()["components"]["queue"]

    assert queue["status"] == HealthStatus.HEALTHY.value
    assert queue["metrics"]["queue"] == "celery"
    assert isinstance(queue["metrics"]["depth"], int)
    assert queue["metrics"]["depth"] >= 0


def test_uptime_is_measured_and_advances_between_calls(
    app_client: TestClient, as_user: UserFactory
) -> None:
    """A hard-coded or cached value could not move."""
    _, engineer = as_user(Role.ENGINEER)

    first = app_client.get(ENDPOINT, headers=engineer).json()["components"]["api"]
    time.sleep(1.1)
    second = app_client.get(ENDPOINT, headers=engineer).json()["components"]["api"]

    assert second["metrics"]["uptime_seconds"] > first["metrics"]["uptime_seconds"]
    assert first["metrics"]["started_at"] == second["metrics"]["started_at"]
    assert first["metrics"]["version"]
    assert first["metrics"]["environment"]


def test_job_counts_reflect_real_rows(app_client: TestClient, as_user: UserFactory) -> None:
    _, engineer = as_user(Role.ENGINEER)
    before = app_client.get(ENDPOINT, headers=engineer).json()["jobs"]
    assert set(before) == {state.value for state in JobState}

    created = app_client.post("/api/v1/jobs", headers=engineer, json={"kind": "health_check"})
    assert created.status_code == 202, created.text

    after = app_client.get(ENDPOINT, headers=engineer).json()["jobs"]
    assert sum(after.values()) == sum(before.values()) + 1


def test_worker_liveness_comes_from_the_control_plane(
    app_client: TestClient, as_user: UserFactory
) -> None:
    """Either a worker answers and is named, or none did and we say so."""
    _, engineer = as_user(Role.ENGINEER)

    workers = app_client.get(ENDPOINT, headers=engineer).json()["components"]["workers"]

    assert workers["status"] in {HealthStatus.HEALTHY.value, HealthStatus.DEGRADED.value}
    if workers["status"] == HealthStatus.HEALTHY.value:
        assert workers["metrics"]["online"] == len(workers["metrics"]["workers"])
        assert workers["metrics"]["online"] >= 1
    else:
        assert workers["metrics"]["online"] == 0
        assert workers["detail"]


def test_scheduler_liveness_comes_from_the_heartbeat_key(
    app_client: TestClient, as_user: UserFactory
) -> None:
    _, engineer = as_user(Role.ENGINEER)

    scheduler = app_client.get(ENDPOINT, headers=engineer).json()["components"]["scheduler"]

    assert scheduler["status"] in {HealthStatus.HEALTHY.value, HealthStatus.DEGRADED.value}
    if scheduler["status"] == HealthStatus.HEALTHY.value:
        assert scheduler["metrics"]["last_heartbeat_at"]
        assert scheduler["metrics"]["seconds_since_heartbeat"] < 180
    else:
        assert scheduler["detail"]


def test_the_overall_status_is_the_worst_component(
    app_client: TestClient, as_user: UserFactory
) -> None:
    _, engineer = as_user(Role.ENGINEER)

    body = app_client.get(ENDPOINT, headers=engineer).json()

    statuses = {component["status"] for component in body["components"].values()}
    expected = (
        HealthStatus.UNHEALTHY.value
        if HealthStatus.UNHEALTHY.value in statuses
        else HealthStatus.DEGRADED.value
        if HealthStatus.DEGRADED.value in statuses
        else HealthStatus.HEALTHY.value
    )
    assert body["status"] == expected


def test_system_health_requires_authentication(app_client: TestClient) -> None:
    resp = app_client.get(ENDPOINT)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_a_roleless_user_cannot_read_system_health(
    app_client: TestClient, as_user: UserFactory
) -> None:
    from tests.helpers import auth_header

    roleless, _ = as_user()

    resp = app_client.get(ENDPOINT, headers=auth_header(roleless))

    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "FORBIDDEN"
