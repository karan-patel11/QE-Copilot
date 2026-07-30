"""Celery application shared by the worker and the scheduler (ADR-0003/0004).

Redis is both broker and result backend. Task definitions live in
``qe_worker.tasks`` and are imported by both the worker and the beat scheduler,
so there is exactly one source of truth for what runs.
"""

from __future__ import annotations

from celery import Celery

from qe_common.config import get_settings


def create_celery_app() -> Celery:
    """Construct the configured Celery application."""
    settings = get_settings()
    app = Celery(
        "qe_copilot",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=["qe_worker.tasks"],
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        result_expires=3600,
        broker_connection_retry_on_startup=True,
    )
    return app


celery_app = create_celery_app()

__all__ = ["celery_app", "create_celery_app"]
