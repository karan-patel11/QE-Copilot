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

    GROQ = "groq"
    MOCK = "mock"


class ModelOperation(StrEnum):
    """What a provider call was *for* — persisted to ``model_runs.operation``.

    Cost and evaluation are both rolled up by this column, so the values are
    coarse pipeline stages rather than function names.
    """

    #: §22.1 requirement decomposition (ADR-0207). Also carries §22 steps 4 and
    #: 5 — entity/constraint extraction and risk identification fold into the
    #: same call rather than getting their own (ADR-0211 Decision 7).
    REQUIREMENT_DECOMPOSITION = "requirement_decomposition"
    #: §22 test-plan generation.
    TEST_PLAN = "test_plan"
    #: §22 detailed test generation.
    TEST_GENERATION = "test_generation"
    #: §22 code generation, Pytest specifically. Framework-specific rather than
    #: generic because §7.1 L229-234 names Playwright and REST-API Python as
    #: initially-supported frameworks too: rows written under one shared
    #: ``code_generation`` value could never be split by framework afterwards,
    #: since ``model_runs`` carries no framework column (ADR-0211 Decision 4).
    PYTEST_CODEGEN = "pytest_codegen"
    #: Reserved for framework-agnostic code generation. **Never written in
    #: Phase 2** — a roll-up seeing these rows knows they came from elsewhere.
    CODE_GENERATION = "code_generation"
    #: Embedding calls, once RAG exists.
    EMBEDDING = "embedding"
    # TODO(phase-5): DEFECT_TRIAGE, LOG_SUMMARISATION


__all__ = ["ModelOperation", "ProviderName"]
