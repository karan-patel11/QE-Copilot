"""Provider interfaces and the shared call orchestration (§18 L1732-1764).

The two ABCs carry §18's signatures verbatim. :class:`RecordingLanguageModel`
sits between them and the concrete adapters and owns everything that must be
true of *every* provider call regardless of vendor: the retry loop, the timing,
and — critically — the guarantee that a ``model_runs`` row is written on every
path, including the ones that raise.

Putting that in a shared base rather than in each adapter is deliberate: an
adapter cannot forget to write the audit row, because it never writes it.
"""

from __future__ import annotations

import asyncio
import decimal
import random
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic

from qe_ai_gateway.contracts import (
    SchemaT,
    StructuredGenerationRequest,
    StructuredGenerationResponse,
    TokenUsage,
)
from qe_ai_gateway.pricing import UnknownModelError, estimate_cost
from qe_ai_gateway.recorder import ModelRunRecord, ModelRunRecorder
from qe_common.errors import (
    ErrorCode,
    ProviderError,
    ProviderRefusalError,
    RetryableProviderError,
)
from qe_common.test_generation import ModelRunStatus
from qe_observability import get_logger

logger = get_logger(__name__)

#: Bounded retries. The provider SDK does its own 429 backoff underneath this;
#: these attempts cover what survives that (ADR-0201 — rate limiting proper is
#: deferred to phase 7).
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_BASE_SECONDS = 0.5
DEFAULT_BACKOFF_MAX_SECONDS = 8.0
DEFAULT_TIMEOUT_SECONDS = 120.0


class GatewayTimeoutError(RetryableProviderError):
    """The gateway's own ``asyncio.wait_for`` deadline elapsed.

    Distinct from a provider-reported timeout only in where it was detected;
    both record ``PROVIDER_TIMEOUT``.
    """

    code = ErrorCode.PROVIDER_TIMEOUT
    http_status = 504


@dataclass(frozen=True, slots=True)
class ProviderCallResult(Generic[SchemaT]):
    """What one adapter attempt returns on success."""

    output: SchemaT
    usage: TokenUsage
    model: str
    stop_reason: str | None = None


class LanguageModelProvider(ABC):
    """§18 L1733-1738. Async, structured, provider-neutral."""

    @abstractmethod
    async def generate_structured(
        self, request: StructuredGenerationRequest[SchemaT]
    ) -> StructuredGenerationResponse[SchemaT]:
        """Generate a response validated against ``request.output_schema``."""
        raise NotImplementedError


class EmbeddingProvider(ABC):
    """§18 L1742-1747.

    No real adapter in Phase 2 — RAG is Phase 5 (§38 L2827); only the mock
    implements this. ``TODO(phase-5)``.
    """

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        raise NotImplementedError


class RecordingLanguageModel(LanguageModelProvider):
    """Retry, timing, cost, and mandatory ``model_runs`` persistence.

    Subclasses implement :meth:`_invoke` — one attempt, no retry, no recording —
    and raise the typed provider errors. Everything else happens here.
    """

    #: Written to ``model_runs.provider``. Subclasses must set it.
    provider_name: str

    def __init__(
        self,
        *,
        recorder: ModelRunRecorder | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
        backoff_max_seconds: float = DEFAULT_BACKOFF_MAX_SECONDS,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")
        self._recorder = recorder
        self._max_attempts = max_attempts
        self._timeout_seconds = timeout_seconds
        self._backoff_base_seconds = backoff_base_seconds
        self._backoff_max_seconds = backoff_max_seconds

    @abstractmethod
    async def _invoke(
        self, request: StructuredGenerationRequest[SchemaT]
    ) -> ProviderCallResult[SchemaT]:
        """Perform exactly one provider call.

        Raise :class:`RetryableProviderError` for transient failures,
        :class:`ProviderRefusalError` for a safety decline,
        :class:`ProviderResponseInvalidError` for a schema violation, or
        :class:`ProviderError` for anything else non-retryable.
        """
        raise NotImplementedError

    @abstractmethod
    def _model_id(self) -> str:
        """The model id to record when a call fails before one is known."""
        raise NotImplementedError

    async def generate_structured(
        self, request: StructuredGenerationRequest[SchemaT]
    ) -> StructuredGenerationResponse[SchemaT]:
        """Run the call with retries, then record it — whatever the outcome."""
        started = time.monotonic()
        attempts = 0
        last_error: ProviderError | None = None

        while attempts < self._max_attempts:
            attempts += 1
            try:
                result = await asyncio.wait_for(
                    self._invoke(request), timeout=self._timeout_seconds
                )
            except TimeoutError as exc:
                # asyncio's own deadline, distinct from the provider reporting one.
                last_error = GatewayTimeoutError(
                    f"{self.provider_name} call exceeded {self._timeout_seconds}s."
                )
                last_error.__cause__ = exc
            except RetryableProviderError as exc:
                last_error = exc
            except ProviderError as exc:
                # Non-retryable — refusals are deterministic and a schema
                # violation will not fix itself on the same input. Covers
                # ProviderRefusalError and ProviderResponseInvalidError, which
                # are both ProviderError subclasses.
                self._record_failure(request, exc, attempts, started)
                raise
            else:
                return self._record_success(request, result, attempts, started)

            if attempts < self._max_attempts:
                await asyncio.sleep(self._backoff_delay(attempts))

        if last_error is None:  # pragma: no cover - loop cannot exit without one
            raise ProviderError(f"{self.provider_name} call failed with no recorded error.")
        self._record_failure(request, last_error, attempts, started)
        raise last_error

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with full jitter, capped.

        Jitter matters because several workers retrying the same provider
        outage in lockstep would otherwise re-converge on the same instant every
        round.
        """
        ceiling = min(self._backoff_base_seconds * (2 ** (attempt - 1)), self._backoff_max_seconds)
        return random.uniform(0.0, ceiling)

    def _record_success(
        self,
        request: StructuredGenerationRequest[SchemaT],
        result: ProviderCallResult[SchemaT],
        attempts: int,
        started: float,
    ) -> StructuredGenerationResponse[SchemaT]:
        latency_ms = _elapsed_ms(started)
        cost = self._estimate(result.model, result.usage)
        run_id = self._record(
            request,
            status=ModelRunStatus.SUCCEEDED,
            model=result.model,
            usage=result.usage,
            cost=cost,
            attempts=attempts,
            latency_ms=latency_ms,
            stop_reason=result.stop_reason,
            error_code=None,
        )
        # Metrics as structured log fields: qe_observability has no counters and
        # OpenTelemetry is P1 (ADR-0209 corrects ADR-0201 on this point).
        logger.info(
            "provider call succeeded",
            extra={
                "provider": self.provider_name,
                "model": result.model,
                "operation": request.operation.value,
                "prompt_version": request.prompt_version_id,
                "latency_ms": latency_ms,
                "attempts": attempts,
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "estimated_cost": str(cost),
            },
        )
        return StructuredGenerationResponse(
            output=result.output,
            model=result.model,
            provider=self.provider_name,
            usage=result.usage,
            estimated_cost=cost,
            latency_ms=latency_ms,
            attempts=attempts,
            stop_reason=result.stop_reason,
            model_run_id=run_id,
        )

    def _record_failure(
        self,
        request: StructuredGenerationRequest[SchemaT],
        error: ProviderError,
        attempts: int,
        started: float,
    ) -> None:
        """Write the audit row for a failed call, then let the error propagate.

        The row is written *before* the exception leaves this class, so a caller
        that swallows the exception still cannot erase the record of the call.
        """
        latency_ms = _elapsed_ms(started)
        refused = isinstance(error, ProviderRefusalError)
        status = ModelRunStatus.REFUSED if refused else ModelRunStatus.FAILED
        model = self._model_id()
        self._record(
            request,
            status=status,
            model=model,
            usage=TokenUsage(),
            cost=self._estimate(model, TokenUsage()),
            attempts=attempts,
            latency_ms=latency_ms,
            stop_reason="refusal" if refused else None,
            error_code=error.code.value,
        )
        logger.warning(
            "provider call failed",
            extra={
                "provider": self.provider_name,
                "model": model,
                "operation": request.operation.value,
                "prompt_version": request.prompt_version_id,
                "latency_ms": latency_ms,
                "attempts": attempts,
                "error_code": error.code.value,
            },
        )

    def _estimate(self, model: str, usage: TokenUsage) -> decimal.Decimal:
        """Cost, or zero for an unpriced model that consumed no tokens.

        A failed call has no tokens to bill, so an unknown model must not turn a
        provider failure into a second, unrelated exception that masks it. A
        *successful* call on an unpriced model still raises — that is a real
        configuration gap and silently recording 0.00 would corrupt cost roll-ups.
        """
        try:
            return estimate_cost(model, usage)
        except UnknownModelError:
            if usage.total_tokens == 0:
                return decimal.Decimal("0")
            raise

    def _record(
        self,
        request: StructuredGenerationRequest[SchemaT],
        *,
        status: ModelRunStatus,
        model: str,
        usage: TokenUsage,
        cost: decimal.Decimal,
        attempts: int,
        latency_ms: int,
        stop_reason: str | None,
        error_code: str | None,
    ) -> uuid.UUID | None:
        if self._recorder is None:
            return None
        return self._recorder.record(
            ModelRunRecord(
                organisation_id=request.organisation_id,
                provider=self.provider_name,
                model=model,
                operation=request.operation,
                status=status,
                usage=usage,
                estimated_cost=cost,
                attempts=attempts,
                prompt_version_id=request.prompt_version_id,
                latency_ms=latency_ms,
                stop_reason=stop_reason,
                error_code=error_code,
                project_id=request.project_id,
                job_id=request.job_id,
                request_id=request.request_id,
            )
        )


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


__all__ = [
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_TIMEOUT_SECONDS",
    "EmbeddingProvider",
    "GatewayTimeoutError",
    "LanguageModelProvider",
    "ProviderCallResult",
    "RecordingLanguageModel",
]
