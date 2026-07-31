"""Deterministic offline provider (ADR-0201, ADR-0206).

The default for CI. No network, no API key, no cost. It validates its canned
payload against the caller's schema, so a fixture that drifts from the schema
fails the test rather than passing a stale shape through — and it can be
programmed to time out, refuse, return malformed JSON, or exhaust retries, which
are the paths that are hardest to trigger against a real provider and easiest to
trigger here.

``MockProvider`` goes through the same :class:`RecordingLanguageModel` machinery
as the real adapter, so the deterministic tier exercises the real retry, timing,
cost, and ``model_runs`` code — not a parallel implementation of it.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

from pydantic import ValidationError

from qe_ai_gateway.base import EmbeddingProvider, ProviderCallResult, RecordingLanguageModel
from qe_ai_gateway.contracts import SchemaT, StructuredGenerationRequest, TokenUsage
from qe_ai_gateway.recorder import ModelRunRecorder
from qe_common.ai import ProviderName
from qe_common.errors import (
    ProviderError,
    ProviderRefusalError,
    ProviderResponseInvalidError,
)

#: Priced at zero in the rate table — the mock makes no provider call.
MOCK_MODEL = "mock-model"

#: Deterministic per-call token counts, so cost assertions are exact.
DEFAULT_MOCK_USAGE = TokenUsage(
    input_tokens=1_000,
    output_tokens=500,
    cache_read_input_tokens=0,
    cache_creation_input_tokens=0,
)


class MockProvider(RecordingLanguageModel, EmbeddingProvider):
    """A scriptable, offline stand-in for a real provider.

    ``responses`` supplies one payload per call, consumed in order; the last is
    reused once exhausted so a test does not have to count calls it does not
    care about. A payload may be a dict, a JSON string, or a callable taking the
    request — the callable form is what lets a test vary output by input.

    ``failures`` schedules exceptions by attempt number, which is how the retry
    path is tested: ``{1: RetryableProviderError(...)}`` fails the first attempt
    and succeeds on the second.
    """

    provider_name = ProviderName.MOCK.value

    def __init__(
        self,
        *,
        responses: Sequence[dict[str, Any] | str | Callable[[Any], dict[str, Any]]] | None = None,
        failures: dict[int, Exception] | None = None,
        usage: TokenUsage = DEFAULT_MOCK_USAGE,
        stop_reason: str | None = "end_turn",
        recorder: ModelRunRecorder | None = None,
        embedding_dimensions: int = 8,
        **kwargs: Any,
    ) -> None:
        super().__init__(recorder=recorder, **kwargs)
        self._responses = list(responses or [])
        self._failures = dict(failures or {})
        self._usage = usage
        self._stop_reason = stop_reason
        self._embedding_dimensions = embedding_dimensions
        self._call_count = 0
        #: Every request the mock has seen — for assertions about what was sent.
        self.seen_requests: list[StructuredGenerationRequest[Any]] = []

    @property
    def call_count(self) -> int:
        """How many attempts have reached the provider (retries included)."""
        return self._call_count

    def _model_id(self) -> str:
        return MOCK_MODEL

    async def _invoke(
        self, request: StructuredGenerationRequest[SchemaT]
    ) -> ProviderCallResult[SchemaT]:
        self._call_count += 1
        self.seen_requests.append(request)

        scheduled = self._failures.get(self._call_count)
        if scheduled is not None:
            raise scheduled

        payload = self._payload_for(request)

        # A refusal arrives as a successful response with no usable content, so
        # it is checked before the body is read — the same order the real
        # adapter uses (ADR-0209).
        if self._stop_reason == "refusal":
            raise ProviderRefusalError("Mock provider refused the request.")

        try:
            output = request.output_schema.model_validate(payload)
        except ValidationError as exc:
            raise ProviderResponseInvalidError(
                f"Mock payload does not satisfy {request.output_schema.__name__}: {exc}"
            ) from exc

        return ProviderCallResult(
            output=output,
            usage=self._usage,
            model=MOCK_MODEL,
            stop_reason=self._stop_reason,
        )

    def _payload_for(self, request: StructuredGenerationRequest[SchemaT]) -> Any:
        """Resolve the next canned payload, parsing JSON strings as a provider would."""
        if not self._responses:
            raise ProviderError(
                "MockProvider was called with no scripted responses. "
                "Pass responses=[...] so the test states what the provider returns."
            )
        index = min(self._call_count - 1, len(self._responses) - 1)
        candidate = self._responses[index]

        if callable(candidate):
            return candidate(request)
        if isinstance(candidate, str):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as exc:
                # The malformed-JSON path N10 needs, surfaced as the same typed
                # error a real provider's unparseable output would produce.
                raise ProviderResponseInvalidError(f"Mock returned malformed JSON: {exc}") from exc
        return candidate

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Deterministic pseudo-embeddings — stable across runs, no network.

        Values derive from the text itself so identical inputs give identical
        vectors, which is what makes similarity assertions reproducible.
        TODO(phase-5): a real embedding adapter arrives with RAG.
        """
        vectors: list[list[float]] = []
        for text in texts:
            seed = sum(ord(char) for char in text) or 1
            vectors.append(
                [((seed * (i + 1)) % 1000) / 1000.0 for i in range(self._embedding_dimensions)]
            )
        return vectors


__all__ = ["DEFAULT_MOCK_USAGE", "MOCK_MODEL", "MockProvider"]
