"""JSON structured logging.

ADR-0007: logs are single-line JSON objects carrying a fixed set of fields so
they can be indexed and correlated across services. Contextual fields
(request_id, trace_id, user_id, project_id, job_id) are bound per request/task
via a :class:`contextvars.ContextVar` and merged into every record.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from contextvars import ContextVar
from typing import Any, TypedDict

from qe_common.config import get_settings

# The mandated log fields, in stable order. Every emitted record contains all of
# them (unset contextual fields serialise as null).
LOG_FIELDS: tuple[str, ...] = (
    "timestamp",
    "service",
    "environment",
    "severity",
    "message",
    "request_id",
    "trace_id",
    "user_id",
    "project_id",
    "job_id",
    "event_type",
    "error_code",
)


class LogContext(TypedDict, total=False):
    """Per-request/per-task contextual fields merged into each log record."""

    request_id: str | None
    trace_id: str | None
    user_id: str | None
    project_id: str | None
    job_id: str | None
    event_type: str | None
    error_code: str | None


# Stored as a plain mapping so arbitrary field names can be bound dynamically;
# :class:`LogContext` documents the fields the platform standardises on.
_log_context: ContextVar[dict[str, Any] | None] = ContextVar("qe_log_context", default=None)


def _current_context() -> dict[str, Any]:
    return dict(_log_context.get() or {})


def bind_log_context(**fields: Any) -> None:
    """Merge ``fields`` into the current logging context.

    Later binds override earlier ones. Pass a field explicitly to clear it.
    """
    current = _current_context()
    current.update(fields)
    _log_context.set(current)


class JsonLogFormatter(logging.Formatter):
    """Render :class:`logging.LogRecord` instances as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        settings = get_settings()
        ctx = _current_context()
        payload: dict[str, Any] = {
            "timestamp": _dt.datetime.fromtimestamp(
                record.created, tz=_dt.UTC
            ).isoformat(),
            "service": getattr(record, "service", settings.service_name),
            "environment": settings.environment,
            "severity": record.levelname,
            "message": record.getMessage(),
            "request_id": ctx.get("request_id"),
            "trace_id": ctx.get("trace_id"),
            "user_id": ctx.get("user_id"),
            "project_id": ctx.get("project_id"),
            "job_id": ctx.get("job_id"),
            "event_type": getattr(record, "event_type", ctx.get("event_type")),
            "error_code": getattr(record, "error_code", ctx.get("error_code")),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str | None = None) -> None:
    """Install the JSON formatter on the root logger (idempotent)."""
    settings = get_settings()
    resolved = (level or settings.log_level).upper()
    root = logging.getLogger()
    root.setLevel(resolved)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root.handlers = [handler]


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Call :func:`configure_logging` once at startup."""
    return logging.getLogger(name)
