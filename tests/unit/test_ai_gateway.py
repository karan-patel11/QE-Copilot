"""N4 unit: gateway behaviour on the MockProvider path (ADR-0206 deterministic tier).

No network, no API key, no database. What is asserted here is the contract that
must hold for *every* adapter, because it lives in the shared
:class:`RecordingLanguageModel` base rather than in either adapter:

* a ``model_runs`` row is written on success, failure, and refusal;
* retries are counted and surfaced;
* cost is computed from all four token classes.
"""

from __future__ import annotations

import contextlib
import decimal
import uuid

import pytest
from pydantic import BaseModel

from qe_ai_gateway import (
    MOCK_MODEL,
    InMemoryModelRunRecorder,
    MockProvider,
    StructuredGenerationRequest,
    TokenUsage,
    UnknownModelError,
    estimate_cost,
)
from qe_ai_gateway.base import GatewayTimeoutError
from qe_common.ai import ModelOperation, ProviderName
from qe_common.errors import (
    ErrorCode,
    ProviderError,
    ProviderRefusalError,
    ProviderResponseInvalidError,
    RetryableProviderError,
)
from qe_common.test_generation import ModelRunStatus

ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


class GeneratedCaseOut(BaseModel):
    """A minimal caller schema — stands in for the real generation schema."""

    title: str
    priority: str


VALID_PAYLOAD = {"title": "Rejects a reused password", "priority": "P0"}


def _request(**overrides: object) -> StructuredGenerationRequest[GeneratedCaseOut]:
    kwargs: dict[str, object] = {
        "prompt": "generate a test",
        "output_schema": GeneratedCaseOut,
        "operation": ModelOperation.TEST_GENERATION,
        "organisation_id": ORG_ID,
        "prompt_version_id": "testgen-v1",
    }
    kwargs.update(overrides)
    return StructuredGenerationRequest(**kwargs)  # type: ignore[arg-type]


# --- success path -----------------------------------------------------------


async def test_success_writes_a_model_runs_row() -> None:
    recorder = InMemoryModelRunRecorder()
    provider = MockProvider(responses=[VALID_PAYLOAD], recorder=recorder)

    response = await provider.generate_structured(_request())

    assert response.output == GeneratedCaseOut(**VALID_PAYLOAD)
    assert response.provider == ProviderName.MOCK.value
    assert len(recorder.runs) == 1
    row = recorder.last
    assert row.status is ModelRunStatus.SUCCEEDED
    assert row.error_code is None
    assert row.attempts == 1
    assert row.organisation_id == ORG_ID
    assert row.operation is ModelOperation.TEST_GENERATION


async def test_prompt_version_id_is_written_through_unmodified() -> None:
    """The gateway must never transform the string it was handed (ADR-0209 §5)."""
    recorder = InMemoryModelRunRecorder()
    provider = MockProvider(responses=[VALID_PAYLOAD], recorder=recorder)

    await provider.generate_structured(_request(prompt_version_id="testgen-v42"))

    assert recorder.last.prompt_version_id == "testgen-v42"


async def test_optional_attribution_columns_are_carried() -> None:
    recorder = InMemoryModelRunRecorder()
    provider = MockProvider(responses=[VALID_PAYLOAD], recorder=recorder)
    project, job, req = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    await provider.generate_structured(_request(project_id=project, job_id=job, request_id=req))

    row = recorder.last
    assert (row.project_id, row.job_id, row.request_id) == (project, job, req)


# --- failure paths ----------------------------------------------------------


async def test_exhausted_retries_write_a_failed_row_and_raise() -> None:
    recorder = InMemoryModelRunRecorder()
    provider = MockProvider(
        responses=[VALID_PAYLOAD],
        failures={i: RetryableProviderError("upstream 503") for i in (1, 2, 3)},
        recorder=recorder,
        max_attempts=3,
        backoff_base_seconds=0.0,
        backoff_max_seconds=0.0,
    )

    with pytest.raises(RetryableProviderError):
        await provider.generate_structured(_request())

    assert provider.call_count == 3
    row = recorder.last
    assert row.status is ModelRunStatus.FAILED
    assert row.error_code == ErrorCode.PROVIDER_ERROR.value
    assert row.attempts == 3


async def test_transient_failure_then_success_is_recorded_once_with_attempts() -> None:
    """Retries stay visible rather than collapsed into one row (ADR-0203)."""
    recorder = InMemoryModelRunRecorder()
    provider = MockProvider(
        responses=[VALID_PAYLOAD],
        failures={1: RetryableProviderError("transient")},
        recorder=recorder,
        backoff_base_seconds=0.0,
        backoff_max_seconds=0.0,
    )

    response = await provider.generate_structured(_request())

    assert response.attempts == 2
    assert len(recorder.runs) == 1
    assert recorder.last.status is ModelRunStatus.SUCCEEDED
    assert recorder.last.attempts == 2


async def test_refusal_is_recorded_as_refused_not_failed() -> None:
    recorder = InMemoryModelRunRecorder()
    provider = MockProvider(responses=[VALID_PAYLOAD], stop_reason="refusal", recorder=recorder)

    with pytest.raises(ProviderRefusalError):
        await provider.generate_structured(_request())

    row = recorder.last
    assert row.status is ModelRunStatus.REFUSED
    assert row.error_code == ErrorCode.PROVIDER_REFUSED.value
    assert row.stop_reason == "refusal"


async def test_refusal_is_not_retried() -> None:
    """A safety decline is deterministic; retrying only burns budget."""
    recorder = InMemoryModelRunRecorder()
    provider = MockProvider(
        responses=[VALID_PAYLOAD],
        stop_reason="refusal",
        recorder=recorder,
        max_attempts=3,
        backoff_base_seconds=0.0,
    )

    with pytest.raises(ProviderRefusalError):
        await provider.generate_structured(_request())

    assert provider.call_count == 1
    assert recorder.last.attempts == 1


async def test_schema_violation_is_recorded_and_not_retried() -> None:
    recorder = InMemoryModelRunRecorder()
    provider = MockProvider(
        responses=[{"title": "missing priority"}],
        recorder=recorder,
        max_attempts=3,
        backoff_base_seconds=0.0,
    )

    with pytest.raises(ProviderResponseInvalidError):
        await provider.generate_structured(_request())

    assert provider.call_count == 1
    row = recorder.last
    assert row.status is ModelRunStatus.FAILED
    assert row.error_code == ErrorCode.PROVIDER_RESPONSE_INVALID.value


async def test_malformed_json_is_recorded_as_a_schema_failure() -> None:
    """The N10 path: unparseable provider output, triggered offline."""
    recorder = InMemoryModelRunRecorder()
    provider = MockProvider(responses=['{"title": "unclosed'], recorder=recorder)

    with pytest.raises(ProviderResponseInvalidError, match="malformed JSON"):
        await provider.generate_structured(_request())

    assert recorder.last.status is ModelRunStatus.FAILED


async def test_timeout_is_recorded_with_the_timeout_error_code() -> None:
    recorder = InMemoryModelRunRecorder()
    provider = MockProvider(
        responses=[VALID_PAYLOAD],
        failures={i: GatewayTimeoutError("too slow") for i in (1, 2)},
        recorder=recorder,
        max_attempts=2,
        backoff_base_seconds=0.0,
    )

    with pytest.raises(GatewayTimeoutError):
        await provider.generate_structured(_request())

    assert recorder.last.error_code == ErrorCode.PROVIDER_TIMEOUT.value
    assert recorder.last.status is ModelRunStatus.FAILED


async def test_every_terminal_outcome_writes_exactly_one_row() -> None:
    """The audit guarantee, stated as one assertion over all four outcomes."""
    cases: list[tuple[MockProvider, type[Exception] | None]] = [
        (MockProvider(responses=[VALID_PAYLOAD]), None),
        (MockProvider(responses=[VALID_PAYLOAD], stop_reason="refusal"), ProviderRefusalError),
        (MockProvider(responses=[{"nope": 1}]), ProviderResponseInvalidError),
        (
            MockProvider(
                responses=[VALID_PAYLOAD],
                failures={1: ProviderError("fatal")},
            ),
            ProviderError,
        ),
    ]
    for provider, expected in cases:
        recorder = InMemoryModelRunRecorder()
        provider._recorder = recorder
        if expected is None:
            await provider.generate_structured(_request())
        else:
            with pytest.raises(expected):
                await provider.generate_structured(_request())
        assert len(recorder.runs) == 1, f"expected one row for {expected}"


async def test_a_swallowed_exception_cannot_erase_the_row() -> None:
    """The row is written before the error leaves the gateway."""
    recorder = InMemoryModelRunRecorder()
    provider = MockProvider(
        responses=[VALID_PAYLOAD],
        failures={1: ProviderError("fatal")},
        recorder=recorder,
    )

    # A careless caller swallowing the failure entirely.
    with contextlib.suppress(ProviderError):
        await provider.generate_structured(_request())

    assert len(recorder.runs) == 1
    assert recorder.last.status is ModelRunStatus.FAILED


# --- cost and token accounting ---------------------------------------------


def test_cost_sums_all_token_classes() -> None:
    """Each class bills at its own rate; folding any into input misprices the call.

    gpt-oss-120b (groq.com/pricing, ADR-0210): in $0.15, cached in $0.075,
    out $0.60, cache write $0 per MTok. With 1M of each class:
        1.00*0.15 + 1.00*0.60 + 1.00*0.075 + 1.00*0 = 0.825000
    """
    usage = TokenUsage(
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_read_input_tokens=1_000_000,
        cache_creation_input_tokens=1_000_000,
    )
    assert estimate_cost("openai/gpt-oss-120b", usage) == decimal.Decimal("0.825000")


def test_cost_of_a_realistic_call() -> None:
    """1200 in / 800 out on the default model.

    1200/1e6*0.15 = 0.000180 ; 800/1e6*0.60 = 0.000480 ; total 0.000660
    """
    usage = TokenUsage(input_tokens=1_200, output_tokens=800)
    assert estimate_cost("openai/gpt-oss-120b", usage) == decimal.Decimal("0.000660")


def test_cached_tokens_bill_at_half_the_input_rate() -> None:
    """Groq's published cached-input discount for the gpt-oss models is 50%.

    100k uncached + 900k cached + 0 out:
        100000/1e6*0.15   = 0.015000
        900000/1e6*0.075  = 0.067500  -> 0.082500
    Billing all 1M at full input rate would be 0.150000, so the discount is real
    and the disjoint split is what makes it computable.
    """
    usage = TokenUsage(input_tokens=100_000, cache_read_input_tokens=900_000)
    assert estimate_cost("openai/gpt-oss-120b", usage) == decimal.Decimal("0.082500")


def test_models_without_published_cache_pricing_get_no_discount() -> None:
    """Assuming a discount would understate cost; assuming none can only overstate.

    llama-3.3-70b-versatile: in $0.59, no cached price published -> cache read
    also $0.59. 500k uncached + 500k cached:
        500000/1e6*0.59 + 500000/1e6*0.59 = 0.295000 + 0.295000 = 0.590000
    """
    usage = TokenUsage(input_tokens=500_000, cache_read_input_tokens=500_000)
    assert estimate_cost("llama-3.3-70b-versatile", usage) == decimal.Decimal("0.590000")


def test_cache_writes_are_free_on_every_model() -> None:
    """Groq provides prompt caching at no additional cost (ADR-0210 §4)."""
    for model in ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.1-8b-instant"):
        usage = TokenUsage(cache_creation_input_tokens=10_000_000)
        assert estimate_cost(model, usage) == decimal.Decimal("0.000000"), model


def test_cost_is_zero_when_no_tokens_were_used() -> None:
    assert estimate_cost("openai/gpt-oss-120b", TokenUsage()) == decimal.Decimal("0.000000")


def test_cost_is_quantised_to_the_column_scale() -> None:
    """model_runs.estimated_cost is NUMERIC(12, 6)."""
    cost = estimate_cost("openai/gpt-oss-120b", TokenUsage(input_tokens=1))
    assert cost.as_tuple().exponent == -6


def test_unpriced_model_raises_rather_than_recording_zero() -> None:
    """A silent 0.00 is indistinguishable from a genuinely free call."""
    with pytest.raises(UnknownModelError):
        estimate_cost("some-unpriced-model", TokenUsage(input_tokens=10))


async def test_token_counts_reach_the_row_unchanged() -> None:
    recorder = InMemoryModelRunRecorder()
    usage = TokenUsage(
        input_tokens=11,
        output_tokens=22,
        cache_read_input_tokens=33,
        cache_creation_input_tokens=44,
    )
    provider = MockProvider(responses=[VALID_PAYLOAD], usage=usage, recorder=recorder)

    response = await provider.generate_structured(_request())

    assert recorder.last.usage == usage
    assert response.usage.total_tokens == 110
    # The mock is priced at zero, so cost is zero regardless of token counts.
    assert recorder.last.estimated_cost == decimal.Decimal("0")
    assert recorder.last.model == MOCK_MODEL


# --- embeddings -------------------------------------------------------------


async def test_mock_embeddings_are_deterministic() -> None:
    provider = MockProvider(responses=[VALID_PAYLOAD])
    first = await provider.embed(["alpha", "beta"])
    second = await provider.embed(["alpha", "beta"])
    assert first == second
    assert len(first) == 2
    assert first[0] != first[1]
