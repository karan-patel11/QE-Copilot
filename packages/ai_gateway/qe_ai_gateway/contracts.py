"""Gateway request/response contracts (§18 L1732-1748).

These types are provider-neutral by construction: nothing here imports a vendor
SDK, so a caller can build a request without knowing which provider will serve
it (§8.5, §18 L1766).
"""

from __future__ import annotations

import decimal
import uuid
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from qe_common.ai import ModelOperation

#: The caller's Pydantic output schema. Structured-output validation is checked
#: against this exact model, so registry and provider contracts cannot drift
#: (ADR-0202).
SchemaT = TypeVar("SchemaT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Token counts for one provider call.

    Cached input is billed at different rates from fresh input, which is why the
    cache fields are carried separately rather than folded into
    ``input_tokens`` — an ``estimated_cost`` computed without them is wrong on
    any cached call (ADR-0203, ADR-0209).
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """Every token class summed — for logging, not for costing."""
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_input_tokens
            + self.cache_creation_input_tokens
        )


@dataclass(frozen=True, slots=True)
class StructuredGenerationRequest(Generic[SchemaT]):
    """One structured-generation call (§18 L1734-1737).

    ``prompt_version_id`` is supplied by the caller and written through
    unmodified. The gateway never constructs it: it holds
    ``prompt_versions.version`` (e.g. ``"testgen-v3"``), and a value invented
    here could not be resolved by the future foreign-key backfill (ADR-0203
    hazard, ADR-0209 Decision 2).
    """

    #: Rendered prompt. Untrusted requirement text is already embedded as *data*
    #: by the prompt template, never as instructions (ADR-0205).
    prompt: str
    #: Pydantic model the response must validate against.
    output_schema: type[SchemaT]
    operation: ModelOperation
    organisation_id: uuid.UUID
    #: ``prompt_versions.version``, resolved by the prompt registry.
    prompt_version_id: str | None = None
    system: str | None = None
    max_tokens: int = 16_000
    project_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    request_id: uuid.UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StructuredGenerationResponse(Generic[SchemaT]):
    """A validated structured-generation result (§18 L1737).

    ``output`` is already an instance of the caller's schema — if the provider
    returned something that did not validate, the call raised rather than
    returning a half-parsed payload.
    """

    output: SchemaT
    model: str
    provider: str
    usage: TokenUsage
    estimated_cost: decimal.Decimal
    latency_ms: int
    attempts: int
    stop_reason: str | None = None
    #: Id of the ``model_runs`` row written for this call, when one was recorded.
    model_run_id: uuid.UUID | None = None


__all__ = [
    "SchemaT",
    "StructuredGenerationRequest",
    "StructuredGenerationResponse",
    "TokenUsage",
]
