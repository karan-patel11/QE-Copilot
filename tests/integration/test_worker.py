"""T5/gate-4 integration: worker runs a task end-to-end via the Redis broker.

Spins up a real Celery worker (consuming from Redis) and dispatches the no-op
health task, asserting the result round-trips through the broker/backend.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from celery.contrib.testing.worker import start_worker

from qe_worker.celery_app import celery_app
from qe_worker.tasks import health_check

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def celery_worker() -> Iterator[None]:
    celery_app.conf.update(broker_connection_retry_on_startup=True)
    with start_worker(celery_app, perform_ping_check=False, shutdown_timeout=30):
        yield None


def test_health_task_via_redis(celery_worker: None) -> None:
    async_result = health_check.delay()
    result = async_result.get(timeout=30)
    assert result == {"status": "ok", "state": "COMPLETED"}
