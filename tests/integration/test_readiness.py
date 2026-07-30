"""T4/gate-3 integration: /readyz returns 200 when Postgres + Redis are live."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from qe_api.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), raise_server_exceptions=False) as c:
        yield c


def test_readyz_200_when_deps_up(client: TestClient) -> None:
    resp = client.get("/readyz")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"database": True, "redis": True}
