"""AI provider gateway — the only module that imports a vendor SDK.

Supersedes the Phase 0 ``AIGateway`` stub, whose ``complete()`` / sync
``embed(text)`` shape did not match §18 (ADR-0201). The interfaces here are
§18 L1732-1748 verbatim.

Owns ``model_runs``. Deliberately does **not** import
:mod:`qe_prompt_registry` and never queries ``prompt_versions``: it receives
``prompt_version_id`` as a parameter and writes it through unmodified, which is
what keeps it structurally unable to invent a version string the future
foreign-key backfill could not resolve (ADR-0203 hazard, ADR-0209 Decision 5).
"""

from __future__ import annotations

from qe_ai_gateway.base import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_TIMEOUT_SECONDS,
    EmbeddingProvider,
    GatewayTimeoutError,
    LanguageModelProvider,
    ProviderCallResult,
    RecordingLanguageModel,
)
from qe_ai_gateway.contracts import (
    StructuredGenerationRequest,
    StructuredGenerationResponse,
    TokenUsage,
)
from qe_ai_gateway.mock import MOCK_MODEL, MockProvider
from qe_ai_gateway.pricing import RATE_TABLE, ModelRates, UnknownModelError, estimate_cost
from qe_ai_gateway.recorder import (
    DatabaseModelRunRecorder,
    InMemoryModelRunRecorder,
    ModelRunRecord,
    ModelRunRecorder,
)

__all__ = [
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_TIMEOUT_SECONDS",
    "MOCK_MODEL",
    "RATE_TABLE",
    "DatabaseModelRunRecorder",
    "EmbeddingProvider",
    "GatewayTimeoutError",
    "InMemoryModelRunRecorder",
    "LanguageModelProvider",
    "MockProvider",
    "ModelRates",
    "ModelRunRecord",
    "ModelRunRecorder",
    "ProviderCallResult",
    "RecordingLanguageModel",
    "StructuredGenerationRequest",
    "StructuredGenerationResponse",
    "TokenUsage",
    "UnknownModelError",
    "estimate_cost",
]

# ``AnthropicProvider`` is intentionally NOT re-exported here: importing this
# package must not pull in the vendor SDK, so the deterministic tier runs even
# with ``anthropic`` uninstalled. Import it explicitly where it is used:
#     from qe_ai_gateway.anthropic_provider import AnthropicProvider
