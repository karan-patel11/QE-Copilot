"""AI-gateway vocabulary shared between the gateway and its callers.

Kept free of ORM and provider imports, like the other ``qe_common`` enums, so a
caller can name an operation without importing either the database or a vendor
SDK (§18 L1766, §37 L2745).
"""

from __future__ import annotations

from enum import StrEnum


class ProviderName(StrEnum):
    """Providers the gateway can route to.

    ``MOCK`` is a first-class member rather than a test-only string: it is
    written to ``model_runs.provider`` by the deterministic tier (ADR-0206), and
    a row that cannot say which provider produced it is not an audit record.
    """

    ANTHROPIC = "anthropic"
    MOCK = "mock"


class ModelOperation(StrEnum):
    """What a provider call was *for* — persisted to ``model_runs.operation``.

    Cost and evaluation are both rolled up by this column, so the values are
    coarse pipeline stages rather than function names.
    """

    #: §22.1 requirement decomposition (ADR-0207).
    REQUIREMENT_DECOMPOSITION = "requirement_decomposition"
    #: §22 detailed test generation.
    TEST_GENERATION = "test_generation"
    #: §22 code generation for a generated case.
    CODE_GENERATION = "code_generation"
    #: Embedding calls, once RAG exists.
    EMBEDDING = "embedding"
    # TODO(phase-5): DEFECT_TRIAGE, LOG_SUMMARISATION


__all__ = ["ModelOperation", "ProviderName"]
