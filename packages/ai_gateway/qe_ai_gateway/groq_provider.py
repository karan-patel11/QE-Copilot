"""Groq adapter — the one place a vendor SDK is imported (§18 L1766, §37 L2745).

ADR-0210 replaced Anthropic with Groq. `design-spec.md` never names a vendor;
§10.3 L591-592 requires only a provider-neutral interface, so the choice is
configuration (``AI_MODEL``) rather than architecture.

Everything vendor-specific is contained here. Retry, timing, cost, and
``model_runs`` persistence all live in :class:`RecordingLanguageModel`, so this
class only translates one call, one usage shape, and one error taxonomy.

Two differences from the previous adapter are semantic rather than mechanical
and are documented in ADR-0210:

* Groq's ``cached_tokens`` is a **subset** of ``prompt_tokens``, so this adapter
  subtracts to keep :class:`TokenUsage` classes disjoint. Mapping them straight
  across would bill every cached token twice.
* Groq has **no refusal signal**, so this adapter never raises
  :class:`ProviderRefusalError`; a content-policy rejection arrives as a
  non-retryable 4xx.
"""

from __future__ import annotations

import json
from typing import Any

import groq
from groq.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from groq.types.chat.completion_create_params import (
    ResponseFormatResponseFormatJsonSchema,
    ResponseFormatResponseFormatJsonSchemaJsonSchema,
)
from pydantic import ValidationError

from qe_ai_gateway.base import GatewayTimeoutError, ProviderCallResult, RecordingLanguageModel
from qe_ai_gateway.contracts import SchemaT, StructuredGenerationRequest, TokenUsage
from qe_ai_gateway.recorder import ModelRunRecorder
from qe_common.ai import ProviderName
from qe_common.config import Settings, get_settings
from qe_common.errors import (
    ProviderError,
    ProviderResponseInvalidError,
    RetryableProviderError,
)
from qe_observability import get_logger

logger = get_logger(__name__)

#: Models where ``strict: true`` engages constrained decoding. Outside this set
#: the request still succeeds, but schema adherence degrades to best-effort and
#: Pydantic re-validation becomes the only real guarantee (ADR-0210 Decision 1).
STRICT_CAPABLE_MODELS = frozenset(
    {
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
    }
)


class GroqProvider(RecordingLanguageModel):
    """Structured generation against Groq's chat-completions API."""

    provider_name = ProviderName.GROQ.value

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: groq.AsyncGroq | None = None,
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

        if self._model not in STRICT_CAPABLE_MODELS:
            # Warn rather than fail: a non-strict model is a degraded-but-working
            # configuration, not an invalid one.
            logger.warning(
                "configured model does not support strict structured output; "
                "schema adherence is best-effort only",
                extra={"model": self._model, "strict_capable": sorted(STRICT_CAPABLE_MODELS)},
            )

    @staticmethod
    def _build_client(settings: Settings) -> groq.AsyncGroq:
        """Construct the SDK client.

        ``max_retries=0`` disables Groq's own retry loop (its default is 2)
        because this gateway owns retries. With both active, one logical call
        makes up to attempts x SDK-retries requests and ``model_runs.attempts``
        under-reports by the SDK's factor — and ADR-0203 added that column
        precisely so retries stay visible.
        """
        if not settings.groq_api_key:
            raise ProviderError(
                "GROQ_API_KEY is not configured. The deterministic test tier "
                "should use MockProvider (ADR-0206); only live tiers need a key."
            )
        return groq.AsyncGroq(
            api_key=settings.groq_api_key,
            timeout=settings.ai_timeout_seconds,
            max_retries=0,
        )

    def _model_id(self) -> str:
        return self._model

    async def _invoke(
        self, request: StructuredGenerationRequest[SchemaT]
    ) -> ProviderCallResult[SchemaT]:
        """One call. No retry here — the base class owns that."""
        messages: list[ChatCompletionMessageParam] = []
        if request.system:
            messages.append(ChatCompletionSystemMessageParam(role="system", content=request.system))
        messages.append(ChatCompletionUserMessageParam(role="user", content=request.prompt))

        response_format = ResponseFormatResponseFormatJsonSchema(
            type="json_schema",
            json_schema=ResponseFormatResponseFormatJsonSchemaJsonSchema(
                name=request.output_schema.__name__,
                strict=True,
                schema=_strictify(request.output_schema.model_json_schema()),
            ),
        )

        try:
            completion = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_completion_tokens=request.max_tokens or self._settings.ai_max_output_tokens,
                response_format=response_format,
            )
            # No temperature / top_p / top_k: output variance is not tuned per
            # request, which is why the deterministic suite runs on MockProvider.
        except groq.APITimeoutError as exc:
            raise GatewayTimeoutError(f"Groq request timed out: {exc}") from exc
        except groq.RateLimitError as exc:
            raise RetryableProviderError(f"Groq rate limited the request: {exc}") from exc
        except groq.APIStatusError as exc:
            raise _status_error(exc) from exc
        except groq.APIConnectionError as exc:
            raise RetryableProviderError(f"Could not reach Groq: {exc}") from exc

        return self._parse(request, completion)

    def _parse(
        self, request: StructuredGenerationRequest[SchemaT], completion: Any
    ) -> ProviderCallResult[SchemaT]:
        choice = completion.choices[0] if completion.choices else None
        if choice is None:
            raise ProviderResponseInvalidError("Groq returned no choices.")

        finish_reason = choice.finish_reason
        # A truncated completion is syntactically incomplete JSON. Naming it here
        # makes the cause legible in model_runs.error_code instead of surfacing
        # as a confusing parse error further down.
        if finish_reason == "length":
            raise ProviderResponseInvalidError(
                "Groq truncated the response at the token limit "
                "(finish_reason='length'); the structured output is incomplete."
            )

        content = choice.message.content
        if not content:
            raise ProviderResponseInvalidError(
                f"Groq returned empty content (finish_reason={finish_reason!r})."
            )

        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProviderResponseInvalidError(f"Groq returned malformed JSON: {exc}") from exc

        try:
            output = request.output_schema.model_validate(payload)
        except ValidationError as exc:
            # With strict mode this should be unreachable; it is the backstop for
            # a non-strict model, where constrained decoding is not in play.
            raise ProviderResponseInvalidError(
                f"Groq output failed {request.output_schema.__name__} validation: {exc}"
            ) from exc

        return ProviderCallResult(
            output=output,
            usage=_usage_from(completion),
            model=getattr(completion, "model", None) or self._model,
            stop_reason=finish_reason,
        )


def _status_error(exc: groq.APIStatusError) -> ProviderError:
    """Map an HTTP status onto the retryable/non-retryable split (ADR-0210).

    5xx and 408/409 are transient. Other 4xx are the caller's fault — including
    a content-policy rejection, which is Groq's nearest equivalent to a refusal
    and is deliberately *not* reported as ``REFUSED``: Groq exposes no refusal
    signal, and synthesising one would put a fabricated distinction into the
    audit record.
    """
    status = exc.status_code
    if status >= 500 or status in {408, 409}:
        return RetryableProviderError(f"Groq returned {status}: {exc}")
    return ProviderError(f"Groq rejected the request with {status}: {exc}")


def _usage_from(completion: Any) -> TokenUsage:
    """Normalise Groq's usage into disjoint :class:`TokenUsage` classes.

    Groq reports ``cached_tokens`` as a **subset** of ``prompt_tokens``, whereas
    :class:`TokenUsage` (and therefore ``estimate_cost``) treats its four fields
    as disjoint counts summed at their own rates. Subtracting here is what keeps
    cached tokens from being billed twice — once at the full input rate inside
    ``prompt_tokens`` and again at the cache rate (ADR-0210 Decision 2).

    Groq has no cache-write concept, so ``cache_creation_input_tokens`` is
    written as an explicit 0 rather than omitted.
    """
    usage = getattr(completion, "usage", None)
    if usage is None:
        return TokenUsage()

    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)

    details = getattr(usage, "prompt_tokens_details", None)
    cached = int(getattr(details, "cached_tokens", 0) or 0) if details else 0
    # Clamp: a cached count exceeding the prompt would make the uncached
    # remainder negative and silently credit the call.
    cached = min(cached, prompt_tokens)

    return TokenUsage(
        input_tokens=prompt_tokens - cached,
        output_tokens=completion_tokens,
        cache_read_input_tokens=cached,
        cache_creation_input_tokens=0,
    )


def _strictify(schema: dict[str, Any]) -> dict[str, Any]:
    """Make a Pydantic JSON schema satisfy Groq's strict-mode requirements.

    Strict mode requires every property to appear in ``required`` and every
    object to set ``additionalProperties: false``; Pydantic's
    ``model_json_schema()`` does neither by default.

    This rewrites the **wire** schema only. Responses are still validated against
    the caller's original Pydantic model, so an optional field stays optional to
    the caller — the model is merely required to emit the key (as ``null``)
    rather than omit it.
    """
    if not isinstance(schema, dict):
        return schema

    result: dict[str, Any] = {}
    for key, value in schema.items():
        if isinstance(value, dict):
            result[key] = _strictify(value)
        elif isinstance(value, list):
            result[key] = [_strictify(v) if isinstance(v, dict) else v for v in value]
        else:
            result[key] = value

    if result.get("type") == "object":
        result["additionalProperties"] = False
        properties = result.get("properties")
        if isinstance(properties, dict):
            result["required"] = list(properties)
    return result


__all__ = ["STRICT_CAPABLE_MODELS", "GroqProvider"]
