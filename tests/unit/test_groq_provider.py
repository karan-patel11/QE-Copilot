"""N4-groq unit: the Groq adapter's translation layer (ADR-0210).

These exercise ``GroqProvider`` with an injected fake client, so there is no
network and no API key — but unlike ``MockProvider`` they go through the real
adapter code: usage normalisation, exception mapping, and schema strictification.

What is *not* tested here is Groq's own behaviour; that needs live credentials
and belongs in the evaluation/contract tier (ADR-0206).
"""

from __future__ import annotations

import contextlib
import decimal
import uuid
from typing import Any

import groq
import httpx
import pytest
from pydantic import BaseModel

from qe_ai_gateway import InMemoryModelRunRecorder, StructuredGenerationRequest, TokenUsage
from qe_ai_gateway.base import GatewayTimeoutError
from qe_ai_gateway.groq_provider import STRICT_CAPABLE_MODELS, GroqProvider, _strictify, _usage_from
from qe_common.ai import ModelOperation, ProviderName
from qe_common.config import Settings
from qe_common.errors import (
    ErrorCode,
    ProviderError,
    ProviderRefusalError,
    ProviderResponseInvalidError,
    RetryableProviderError,
)
from qe_common.test_generation import ModelRunStatus

ORG_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
DEFAULT_MODEL = "openai/gpt-oss-120b"


class CaseOut(BaseModel):
    title: str
    priority: str


VALID_JSON = '{"title": "Rejects a reused password", "priority": "P0"}'


# --- fakes -----------------------------------------------------------------


class _Usage:
    def __init__(
        self, prompt: int, completion: int, cached: int | None = None, reasoning: int | None = None
    ) -> None:
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.total_tokens = prompt + completion
        self.prompt_tokens_details = type("D", (), {"cached_tokens": cached})() if cached else None
        self.completion_tokens_details = (
            type("D", (), {"reasoning_tokens": reasoning})() if reasoning else None
        )


class _Completion:
    def __init__(
        self,
        content: str | None = VALID_JSON,
        finish_reason: str = "stop",
        usage: _Usage | None = None,
        model: str = DEFAULT_MODEL,
        choices: bool = True,
    ) -> None:
        message = type("M", (), {"content": content})()
        choice = type("C", (), {"message": message, "finish_reason": finish_reason})()
        self.choices = [choice] if choices else []
        self.usage = usage or _Usage(1_200, 800)
        self.model = model


class _FakeCompletions:
    """Stands in for ``client.chat.completions``."""

    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self._result = result if result is not None else _Completion()
        self._error = error
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._result


class _FakeClient:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.chat = type("Chat", (), {"completions": completions})()


def _settings(model: str = DEFAULT_MODEL) -> Settings:
    return Settings(GROQ_API_KEY="test-key", AI_MODEL=model)


def _provider(
    completions: _FakeCompletions,
    *,
    recorder: InMemoryModelRunRecorder | None = None,
    model: str = DEFAULT_MODEL,
    **kwargs: Any,
) -> GroqProvider:
    kwargs.setdefault("backoff_base_seconds", 0.0)
    kwargs.setdefault("backoff_max_seconds", 0.0)
    return GroqProvider(
        settings=_settings(model),
        client=_FakeClient(completions),  # type: ignore[arg-type]
        recorder=recorder,
        **kwargs,
    )


def _request(**overrides: object) -> StructuredGenerationRequest[CaseOut]:
    kwargs: dict[str, Any] = {
        "prompt": "generate a test",
        "output_schema": CaseOut,
        "operation": ModelOperation.TEST_GENERATION,
        "organisation_id": ORG_ID,
        "prompt_version_id": "testgen-v1",
    }
    kwargs.update(overrides)
    return StructuredGenerationRequest(**kwargs)


def _status_error(status: int) -> groq.APIStatusError:
    """Build a real SDK status error, so the mapping is tested against the real type."""
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status, request=request, json={"error": {"message": "x"}})
    return groq.APIStatusError("boom", response=response, body=None)


# --- usage normalisation (the correctness-critical part) --------------------


def test_usage_maps_prompt_and_completion_tokens() -> None:
    usage = _usage_from(_Completion(usage=_Usage(1_200, 800)))
    assert usage == TokenUsage(
        input_tokens=1_200,
        output_tokens=800,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )


def test_cached_tokens_are_subtracted_from_prompt_tokens() -> None:
    """Groq reports cached_tokens INSIDE prompt_tokens (ADR-0210 §2).

    Mapping them straight across would bill 900 tokens twice: once at the full
    input rate inside prompt_tokens, once again at the cache rate.
    """
    usage = _usage_from(_Completion(usage=_Usage(1_000, 500, cached=900)))
    assert usage.input_tokens == 100
    assert usage.cache_read_input_tokens == 900
    # Reconciles with Groq's own total: (1000-900) + 500 + 900 + 0 == 1500.
    assert usage.total_tokens == 1_500


def test_cache_creation_is_always_zero() -> None:
    """Groq has no cache-write concept; 0 is honest, NULL would say 'unknown'."""
    usage = _usage_from(_Completion(usage=_Usage(10, 5, cached=3)))
    assert usage.cache_creation_input_tokens == 0


def test_cached_tokens_exceeding_prompt_tokens_are_clamped() -> None:
    """A negative uncached remainder would silently credit the call."""
    usage = _usage_from(_Completion(usage=_Usage(100, 50, cached=500)))
    assert usage.input_tokens == 0
    assert usage.cache_read_input_tokens == 100


def test_reasoning_tokens_are_not_added_to_output() -> None:
    """completion_tokens is taken as authoritative (ADR-0210 open item).

    Adding reasoning_tokens on top would double-count under the standard
    subset convention.
    """
    usage = _usage_from(_Completion(usage=_Usage(100, 50, reasoning=40)))
    assert usage.output_tokens == 50


def test_missing_usage_object_yields_zeros_not_an_error() -> None:
    completion = _Completion()
    completion.usage = None  # type: ignore[assignment]
    assert _usage_from(completion) == TokenUsage()


# --- schema strictification -------------------------------------------------


def test_strictify_requires_all_properties_and_forbids_extras() -> None:
    strict = _strictify(CaseOut.model_json_schema())
    assert strict["additionalProperties"] is False
    assert sorted(strict["required"]) == ["priority", "title"]


def test_strictify_promotes_optional_fields_to_required() -> None:
    """Strict mode has no notion of optional; the key must be emitted as null."""

    class WithOptional(BaseModel):
        title: str
        note: str | None = None

    strict = _strictify(WithOptional.model_json_schema())
    assert sorted(strict["required"]) == ["note", "title"]


def test_strictify_recurses_into_nested_objects() -> None:
    nested = {
        "type": "object",
        "properties": {
            "outer": {"type": "object", "properties": {"inner": {"type": "string"}}},
        },
    }
    strict = _strictify(nested)
    inner = strict["properties"]["outer"]
    assert inner["additionalProperties"] is False
    assert inner["required"] == ["inner"]


async def test_request_sends_strict_json_schema() -> None:
    completions = _FakeCompletions()
    provider = _provider(completions)

    await provider.generate_structured(_request())

    sent = completions.calls[0]["response_format"]
    assert sent["type"] == "json_schema"
    assert sent["json_schema"]["strict"] is True
    assert sent["json_schema"]["name"] == "CaseOut"
    assert sent["json_schema"]["schema"]["additionalProperties"] is False


async def test_system_prompt_becomes_a_system_message() -> None:
    completions = _FakeCompletions()
    provider = _provider(completions)

    await provider.generate_structured(_request(system="you are a QE"))

    roles = [m["role"] for m in completions.calls[0]["messages"]]
    assert roles == ["system", "user"]


async def test_no_sampling_parameters_are_sent() -> None:
    """Nothing sets temperature/top_p — output variance is not tuned per request."""
    completions = _FakeCompletions()
    provider = _provider(completions)

    await provider.generate_structured(_request())

    assert not {"temperature", "top_p", "top_k"} & set(completions.calls[0])


def test_default_model_supports_strict_structured_output() -> None:
    assert DEFAULT_MODEL in STRICT_CAPABLE_MODELS


# --- success path -----------------------------------------------------------


async def test_success_writes_a_model_runs_row() -> None:
    recorder = InMemoryModelRunRecorder()
    provider = _provider(_FakeCompletions(), recorder=recorder)

    response = await provider.generate_structured(_request())

    assert response.output == CaseOut(title="Rejects a reused password", priority="P0")
    assert response.provider == ProviderName.GROQ.value
    row = recorder.last
    assert row.status is ModelRunStatus.SUCCEEDED
    assert row.error_code is None
    assert row.attempts == 1
    assert row.prompt_version_id == "testgen-v1"
    # 1200 in / 800 out on gpt-oss-120b -> 0.000660
    assert row.estimated_cost == decimal.Decimal("0.000660")


# --- failure paths ----------------------------------------------------------


@pytest.mark.parametrize("status", [500, 502, 503, 408, 409])
async def test_transient_statuses_are_retried(status: int) -> None:
    recorder = InMemoryModelRunRecorder()
    provider = _provider(
        _FakeCompletions(error=_status_error(status)), recorder=recorder, max_attempts=3
    )

    with pytest.raises(RetryableProviderError):
        await provider.generate_structured(_request())

    assert recorder.last.attempts == 3
    assert recorder.last.status is ModelRunStatus.FAILED


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
async def test_client_errors_are_not_retried(status: int) -> None:
    """Includes 400/422 — Groq's nearest equivalent to a content-policy refusal."""
    recorder = InMemoryModelRunRecorder()
    provider = _provider(
        _FakeCompletions(error=_status_error(status)), recorder=recorder, max_attempts=3
    )

    with pytest.raises(ProviderError) as caught:
        await provider.generate_structured(_request())

    assert not isinstance(caught.value, RetryableProviderError)
    assert recorder.last.attempts == 1
    assert recorder.last.status is ModelRunStatus.FAILED
    assert recorder.last.error_code == ErrorCode.PROVIDER_ERROR.value


async def test_groq_never_reports_a_refusal_status() -> None:
    """Groq exposes no refusal signal, so REFUSED must not be synthesised.

    A content-policy rejection is a non-retryable 4xx and is recorded as FAILED.
    ``ModelRunStatus.REFUSED`` stays reachable via MockProvider for N10.
    """
    recorder = InMemoryModelRunRecorder()
    provider = _provider(_FakeCompletions(error=_status_error(400)), recorder=recorder)

    with pytest.raises(ProviderError) as caught:
        await provider.generate_structured(_request())

    assert not isinstance(caught.value, ProviderRefusalError)
    assert recorder.last.status is not ModelRunStatus.REFUSED
    assert recorder.last.stop_reason is None


async def test_rate_limit_is_retried() -> None:
    request = httpx.Request("POST", "https://api.groq.com/")
    response = httpx.Response(429, request=request, json={"error": {"message": "slow down"}})
    recorder = InMemoryModelRunRecorder()
    provider = _provider(
        _FakeCompletions(error=groq.RateLimitError("429", response=response, body=None)),
        recorder=recorder,
        max_attempts=2,
    )

    with pytest.raises(RetryableProviderError):
        await provider.generate_structured(_request())

    assert recorder.last.attempts == 2


async def test_timeout_is_recorded_with_the_timeout_code() -> None:
    recorder = InMemoryModelRunRecorder()
    request = httpx.Request("POST", "https://api.groq.com/")
    provider = _provider(
        _FakeCompletions(error=groq.APITimeoutError(request=request)),
        recorder=recorder,
        max_attempts=2,
    )

    with pytest.raises(GatewayTimeoutError):
        await provider.generate_structured(_request())

    assert recorder.last.error_code == ErrorCode.PROVIDER_TIMEOUT.value
    assert recorder.last.attempts == 2


async def test_connection_error_is_retried() -> None:
    recorder = InMemoryModelRunRecorder()
    request = httpx.Request("POST", "https://api.groq.com/")
    provider = _provider(
        _FakeCompletions(error=groq.APIConnectionError(request=request)),
        recorder=recorder,
        max_attempts=2,
    )

    with pytest.raises(RetryableProviderError):
        await provider.generate_structured(_request())

    assert recorder.last.attempts == 2


async def test_malformed_json_is_a_schema_failure_and_is_not_retried() -> None:
    recorder = InMemoryModelRunRecorder()
    provider = _provider(
        _FakeCompletions(_Completion(content='{"title": "unclosed')),
        recorder=recorder,
        max_attempts=3,
    )

    with pytest.raises(ProviderResponseInvalidError, match="malformed JSON"):
        await provider.generate_structured(_request())

    assert recorder.last.attempts == 1
    assert recorder.last.error_code == ErrorCode.PROVIDER_RESPONSE_INVALID.value


async def test_schema_violation_is_not_retried() -> None:
    recorder = InMemoryModelRunRecorder()
    provider = _provider(
        _FakeCompletions(_Completion(content='{"title": "no priority field"}')),
        recorder=recorder,
        max_attempts=3,
    )

    with pytest.raises(ProviderResponseInvalidError):
        await provider.generate_structured(_request())

    assert recorder.last.attempts == 1


async def test_truncated_response_is_named_explicitly() -> None:
    """finish_reason='length' yields incomplete JSON — a Groq-specific mode."""
    recorder = InMemoryModelRunRecorder()
    provider = _provider(
        _FakeCompletions(_Completion(content='{"title": "tru', finish_reason="length")),
        recorder=recorder,
    )

    with pytest.raises(ProviderResponseInvalidError, match="truncated"):
        await provider.generate_structured(_request())

    assert recorder.last.error_code == ErrorCode.PROVIDER_RESPONSE_INVALID.value


async def test_empty_content_is_a_schema_failure() -> None:
    recorder = InMemoryModelRunRecorder()
    provider = _provider(_FakeCompletions(_Completion(content=None)), recorder=recorder)

    with pytest.raises(ProviderResponseInvalidError, match="empty content"):
        await provider.generate_structured(_request())

    assert len(recorder.runs) == 1


async def test_no_choices_is_a_schema_failure() -> None:
    recorder = InMemoryModelRunRecorder()
    provider = _provider(_FakeCompletions(_Completion(choices=False)), recorder=recorder)

    with pytest.raises(ProviderResponseInvalidError, match="no choices"):
        await provider.generate_structured(_request())

    assert len(recorder.runs) == 1


async def test_a_swallowed_exception_cannot_erase_the_row() -> None:
    recorder = InMemoryModelRunRecorder()
    provider = _provider(_FakeCompletions(error=_status_error(400)), recorder=recorder)

    with contextlib.suppress(ProviderError):
        await provider.generate_structured(_request())

    assert len(recorder.runs) == 1
    assert recorder.last.status is ModelRunStatus.FAILED


async def test_retries_are_surfaced_not_collapsed() -> None:
    """The gateway owns retries; the SDK client is built with max_retries=0."""
    recorder = InMemoryModelRunRecorder()
    provider = _provider(
        _FakeCompletions(error=_status_error(503)), recorder=recorder, max_attempts=3
    )

    with pytest.raises(RetryableProviderError):
        await provider.generate_structured(_request())

    assert len(recorder.runs) == 1
    assert recorder.last.attempts == 3


def test_client_is_constructed_with_sdk_retries_disabled() -> None:
    """Groq's SDK default is 2; both loops retrying would under-report attempts."""
    client = GroqProvider._build_client(_settings())
    assert client.max_retries == 0


def test_missing_api_key_fails_loudly() -> None:
    with pytest.raises(ProviderError, match="GROQ_API_KEY"):
        GroqProvider._build_client(Settings(GROQ_API_KEY=None))


def test_non_strict_model_warns_but_still_constructs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A non-strict model is degraded-but-working, not invalid."""
    with caplog.at_level("WARNING"):
        provider = _provider(_FakeCompletions(), model="llama-3.3-70b-versatile")
    assert provider is not None
    assert any("strict" in record.message for record in caplog.records)
