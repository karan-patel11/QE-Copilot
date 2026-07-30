"""T4 PASS: API shell — healthz, ping, OpenAPI, readyz-down, error format."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from qe_api import health
from qe_api.main import create_app


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), raise_server_exceptions=False) as c:
        yield c


def test_healthz_always_ok(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ping(client: TestClient) -> None:
    resp = client.get("/api/v1/ping")
    assert resp.status_code == 200
    assert resp.json() == {"message": "pong"}


def test_openapi_generates(client: TestClient) -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["info"]["title"] == "QE Copilot API"
    assert "/api/v1/ping" in spec["paths"]


def test_correlation_id_echoed(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.headers.get("X-Request-ID")


def test_readyz_503_when_deps_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _down() -> bool:
        return False

    monkeypatch.setattr(health, "_check_database", _down)
    monkeypatch.setattr(health, "_check_redis", _down)
    resp = client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"] == {"database": False, "redis": False}


def test_error_envelope_on_not_found(client: TestClient) -> None:
    resp = client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert set(body["error"].keys()) == {"code", "message", "request_id", "details"}
    assert body["error"]["code"] == "NOT_FOUND"
