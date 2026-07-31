"""Persistence of ``model_runs`` rows (ADR-0209 Decision 4/5).

``model_runs`` is owned by this package (§12.2 table ownership). The gateway does
not own transaction boundaries, so the recorder is injected: the default writes
through :mod:`qe_database`, and tests use the in-memory one.

**A row is written on every call — success, failure, and refusal.** The row is
the audit record; the failure paths are the ones that make it worth having.
"""

from __future__ import annotations

import decimal
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.orm import Session

from qe_ai_gateway.contracts import TokenUsage
from qe_common.ai import ModelOperation
from qe_common.test_generation import ModelRunStatus
from qe_database.models import ModelRun
from qe_observability import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class ModelRunRecord:
    """Everything one ``model_runs`` row carries, provider-neutrally."""

    organisation_id: uuid.UUID
    provider: str
    model: str
    operation: ModelOperation
    status: ModelRunStatus
    usage: TokenUsage
    estimated_cost: decimal.Decimal
    attempts: int
    #: ``prompt_versions.version`` — a plain string, never a UUID. Not an FK.
    prompt_version_id: str | None = None
    latency_ms: int | None = None
    stop_reason: str | None = None
    error_code: str | None = None
    project_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    request_id: uuid.UUID | None = None


class ModelRunRecorder(Protocol):
    """Writes one ``model_runs`` row and returns its id."""

    def record(self, run: ModelRunRecord) -> uuid.UUID | None:
        """Persist ``run``. Must not raise for an ordinary failed call."""
        ...


def _to_model_run(run: ModelRunRecord) -> ModelRun:
    """Build the ORM row. Shared so the two recorders cannot drift apart."""
    return ModelRun(
        organisation_id=run.organisation_id,
        project_id=run.project_id,
        job_id=run.job_id,
        request_id=run.request_id,
        provider=run.provider,
        model=run.model,
        operation=run.operation.value,
        prompt_version_id=run.prompt_version_id,
        input_token_count=run.usage.input_tokens,
        output_token_count=run.usage.output_tokens,
        cache_read_input_tokens=run.usage.cache_read_input_tokens,
        cache_creation_input_tokens=run.usage.cache_creation_input_tokens,
        estimated_cost=run.estimated_cost,
        latency_ms=run.latency_ms,
        status=run.status.value,
        stop_reason=run.stop_reason,
        error_code=run.error_code,
        attempts=run.attempts,
    )


class DatabaseModelRunRecorder:
    """Writes through a SQLAlchemy session supplied by the caller.

    Takes a session rather than opening one so the row joins whatever
    transaction the calling pipeline already has open (ADR-0204). Use this when
    the caller *is* the audit boundary; use :class:`CommittingModelRunRecorder`
    when the caller may roll back work the provider has already billed for.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def record(self, run: ModelRunRecord) -> uuid.UUID | None:
        row = _to_model_run(run)
        self._session.add(row)
        self._session.flush()
        return row.id


class CommittingModelRunRecorder:
    """Writes each row in its own transaction, committed immediately.

    Metering must outlive the pipeline that produced it (ADR-0211 Decision 2).
    A generation that fails at a late stage rolls back its transaction — and if
    ``model_runs`` rows rode along in it, the audit record of provider calls that
    **actually happened and actually cost money** would be destroyed by the
    failure of an unrelated downstream step.

    A ``SAVEPOINT`` would not help: nested transactions roll back with their
    parent. Only a genuinely separate transaction survives, so this takes a
    session *factory* and opens its own short-lived session per row.

    Requires the ``request_id`` / ``job_id`` foreign-key targets to be committed
    already — which ADR-0204's flow guarantees, since the API commits the
    request and job rows before dispatching the job.
    """

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def record(self, run: ModelRunRecord) -> uuid.UUID | None:
        """Persist ``run`` in its own transaction.

        Never raises. A failure here would otherwise replace an in-flight
        provider exception with a persistence one, and the operator would lose
        the actual failure. Instead the whole record is logged at ERROR, so the
        metering data survives in the log stream even when the row does not —
        loud, not silent (§37 L2746).
        """
        try:
            with self._session_factory() as session:
                row = _to_model_run(run)
                session.add(row)
                session.commit()
                return row.id
        except Exception as exc:
            logger.error(
                "model_runs row could not be persisted; metering retained in logs only",
                exc_info=exc,
                extra={
                    "event_type": "model_run.persist_failed",
                    "provider": run.provider,
                    "model": run.model,
                    "operation": run.operation.value,
                    "status": run.status.value,
                    "prompt_version": run.prompt_version_id,
                    "input_tokens": run.usage.input_tokens,
                    "output_tokens": run.usage.output_tokens,
                    "cache_read_input_tokens": run.usage.cache_read_input_tokens,
                    "cache_creation_input_tokens": run.usage.cache_creation_input_tokens,
                    "estimated_cost": str(run.estimated_cost),
                    "attempts": run.attempts,
                    "latency_ms": run.latency_ms,
                    "error_code": run.error_code,
                    "organisation_id": str(run.organisation_id),
                    "request_id": str(run.request_id) if run.request_id else None,
                    "job_id": str(run.job_id) if run.job_id else None,
                },
            )
            return None


@dataclass(slots=True)
class InMemoryModelRunRecorder:
    """Collects rows in a list. Used by the deterministic tier (ADR-0206)."""

    runs: list[ModelRunRecord] = field(default_factory=list)

    def record(self, run: ModelRunRecord) -> uuid.UUID | None:
        self.runs.append(run)
        return None

    @property
    def last(self) -> ModelRunRecord:
        """The most recent row, for assertions."""
        if not self.runs:
            raise AssertionError("No model_runs row was recorded.")
        return self.runs[-1]


__all__ = [
    "CommittingModelRunRecorder",
    "DatabaseModelRunRecorder",
    "InMemoryModelRunRecorder",
    "ModelRunRecord",
    "ModelRunRecorder",
]
