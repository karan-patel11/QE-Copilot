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
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.orm import Session

from qe_ai_gateway.contracts import TokenUsage
from qe_common.ai import ModelOperation
from qe_common.test_generation import ModelRunStatus
from qe_database.models import ModelRun


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


class DatabaseModelRunRecorder:
    """Writes through a SQLAlchemy session supplied by the caller.

    Takes a session rather than opening one so the row joins whatever
    transaction the calling pipeline already has open (ADR-0204).
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def record(self, run: ModelRunRecord) -> uuid.UUID | None:
        row = ModelRun(
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
        self._session.add(row)
        self._session.flush()
        return row.id


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
    "DatabaseModelRunRecorder",
    "InMemoryModelRunRecorder",
    "ModelRunRecord",
    "ModelRunRecorder",
]
