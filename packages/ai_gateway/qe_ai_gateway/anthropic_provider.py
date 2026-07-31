"""Anthropic adapter — the one place the vendor SDK is imported (§18 L1766, §37 L2745).

ADR-0201 selected Anthropic and ``claude-opus-5`` as an *inference*: the spec
requires a provider-neutral interface but never names a vendor. The model id is
configurable (``AI_MODEL``), so the choice is an env change rather than a code
change — which is what provider-neutrality actually has to mean.

Everything vendor-specific is contained here. Retry, timing, cost, and
``model_runs`` persistence all live in :class:`RecordingLanguageModel`, so this
class only has to translate one call and one error taxonomy.
"""

from __future__ import annotations

from typing import Any

import anthropic
from pydantic import ValidationError

from qe_ai_gateway.base import GatewayTimeoutError, ProviderCallResult, RecordingLanguageModel
from qe_ai_gateway.contracts import SchemaT, StructuredGenerationRequest, TokenUsage
from qe_ai_gateway.recorder import ModelRunRecorder
from qe_common.ai import ProviderName
from qe_common.config import Settings, get_settings
from qe_common.errors import (
    ProviderError,
    ProviderRefusalError,
    ProviderResponseInvalidError,
    RetryableProviderError,
)


class AnthropicProvider(RecordingLanguageModel):
    """Structured generation against the Anthropic Messages API."""

    provider_name = ProviderName.ANTHROPIC.value

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: anthropic.AsyncAnthropic | None = None,
        recorder: ModelRunRecorder | None = None,
        **kwargs: Any,
    ) -> None:
        resolved = settings or get_settings()
        kwargs.setdefault("timeout_seconds", resolved.ai_timeout_seconds)
        kwargs.setdefault("max_attempts", resolved.ai_max_attempts)
        super().__init__(recorder=recorder, **kwargs)
        self._settings = resolved
        self._model = resolved.ai_model
        self._client = client or self._build_client(resolved)

    @staticmethod
    def _build_client(settings: Settings) -> anthropic.AsyncAnthropic:
        """Construct the SDK client.

        ``max_retries=0`` disables the SDK's own retry loop because this gateway
        owns retries. With both active, one logical call would make up to
        attempts x SDK-retries requests and ``model_runs.attempts`` would
        under-report by the SDK's factor — and ADR-0203 added that column
        specifically so retries stay visible rather than collapsed.
        """
        if not settings.anthropic_api_key:
            raise ProviderError(
                "ANTHROPIC_API_KEY is not configured. The deterministic test tier "
                "should use MockProvider (ADR-0206); only live tiers need a key."
            )
        return anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.ai_timeout_seconds,
            max_retries=0,
        )

    def _model_id(self) -> str:
        return self._model

    async def _invoke(
        self, request: StructuredGenerationRequest[SchemaT]
    ) -> ProviderCallResult[SchemaT]:
        """One call. No retry here — the base class owns that."""
        try:
            response = await self._client.messages.parse(
                model=self._model,
                max_tokens=request.max_tokens or self._settings.ai_max_output_tokens,
                system=request.system or anthropic.omit,
                messages=[{"role": "user", "content": request.prompt}],
                output_format=request.output_schema,
            )
            # temperature / top_p / top_k / thinking.budget_tokens are never
            # sent: all four are rejected with a 400 on this model, and thinking
            # is on by default (ADR-0201, ADR-0209).
        except anthropic.APITimeoutError as exc:
            raise GatewayTimeoutError(f"Anthropic request timed out: {exc}") from exc
        except anthropic.RateLimitError as exc:
            raise RetryableProviderError(f"Anthropic rate limited the request: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise _status_error(exc) from exc
        except anthropic.APIConnectionError as exc:
            raise RetryableProviderError(f"Could not reach Anthropic: {exc}") from exc

        # A refusal is HTTP 200 with empty or partial content, so stop_reason is
        # checked *before* the body is touched (ADR-0201, ADR-0209).
        if response.stop_reason == "refusal":
            raise ProviderRefusalError(
                f"Anthropic declined the request (category: {_refusal_category(response)})."
            )

        # ``parsed_output`` is None when no text block carried a parsed payload —
        # e.g. the turn stopped at max_tokens mid-object. Treat that as a schema
        # failure rather than letting a None reach the pipeline.
        parsed = response.parsed_output
        if parsed is None:
            raise ProviderResponseInvalidError(
                "Anthropic returned no parsed output for a structured request "
                f"(stop_reason={response.stop_reason!r})."
            )
        try:
            output = request.output_schema.model_validate(parsed)
        except ValidationError as exc:
            # The SDK already validated against the schema; this re-check exists
            # so a shape that slipped through arrives as a typed failure rather
            # than as a half-parsed object deeper in the pipeline.
            raise ProviderResponseInvalidError(
                f"Anthropic output failed {request.output_schema.__name__} validation: {exc}"
            ) from exc

        return ProviderCallResult(
            output=output,
            usage=_usage_from(response),
            model=response.model,
            stop_reason=response.stop_reason,
        )


def _status_error(exc: anthropic.APIStatusError) -> ProviderError:
    """Map an HTTP status onto the retryable/non-retryable split.

    5xx and 408/409 are transient; other 4xx are the caller's fault and retrying
    an identical request would only burn budget (ADR-0201).
    """
    status = exc.status_code
    if status >= 500 or status in {408, 409}:
        return RetryableProviderError(f"Anthropic returned {status}: {exc}")
    return ProviderError(f"Anthropic rejected the request with {status}: {exc}")


def _refusal_category(response: Any) -> str:
    """Refusal category when the SDK supplies one.

    ``stop_details`` is informational and may be absent or null even on a
    refusal, so this never gates the refusal itself — only its label.
    """
    details = getattr(response, "stop_details", None)
    category = getattr(details, "category", None)
    return str(category) if category else "unspecified"


def _usage_from(response: Any) -> TokenUsage:
    """Read token counts, treating every field as optional.

    A usage field the SDK omits must read as zero rather than raise: losing the
    whole ``model_runs`` row over a missing counter would trade a complete audit
    record for a partial one.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return TokenUsage()
    return TokenUsage(
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        cache_read_input_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        cache_creation_input_tokens=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
    )


__all__ = ["AnthropicProvider"]
