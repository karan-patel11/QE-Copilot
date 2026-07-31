"""Test generation — the §22 pipeline (ADR-0205, ADR-0207, ADR-0208, ADR-0211).

Decompose a requirement, plan coverage, generate cases, generate Pytest, validate
statically, persist for human review. Nothing auto-approves (§8.2) and nothing
executes generated code (§23 L1991).

This package calls :mod:`qe_ai_gateway` and never a vendor SDK (§18 L1766,
§37 L2745), and resolves every prompt through :mod:`qe_prompt_registry` so
``model_runs.prompt_version_id`` only ever holds strings the registry issued.
"""

from __future__ import annotations

from qe_test_generation.config import (
    MAX_NUMBER_OF_TESTS,
    TestGeneratorConfig,
    assert_supported,
    resolve_configuration,
    validate_configuration,
)
from qe_test_generation.contracts import (
    DECOMPOSITION_FIELDS,
    Decomposition,
    GeneratedCase,
    GeneratedCases,
    GeneratedCode,
    GeneratedCodeSet,
    PlannedCase,
    TestPlan,
    decomposition_summary,
)
from qe_test_generation.persistence import build_summary, persist_cases
from qe_test_generation.pipeline import (
    GenerationOutcome,
    StageOutputs,
    cases_for_request,
    run_generation,
)
from qe_test_generation.stages import GenerationContext, resolve_prompts
from qe_test_generation.validation import (
    CaseValidation,
    ValidationFinding,
    validate_case,
)

__all__ = [
    "DECOMPOSITION_FIELDS",
    "MAX_NUMBER_OF_TESTS",
    "CaseValidation",
    "Decomposition",
    "GeneratedCase",
    "GeneratedCases",
    "GeneratedCode",
    "GeneratedCodeSet",
    "GenerationContext",
    "GenerationOutcome",
    "PlannedCase",
    "StageOutputs",
    "TestGeneratorConfig",
    "TestPlan",
    "ValidationFinding",
    "assert_supported",
    "build_summary",
    "cases_for_request",
    "decomposition_summary",
    "persist_cases",
    "resolve_configuration",
    "resolve_prompts",
    "run_generation",
    "validate_case",
    "validate_configuration",
]
