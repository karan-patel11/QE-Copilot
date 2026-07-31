"""Prompt registry — versioned, lifecycle-managed prompt assets (ADR-0209).

Owns ``prompt_versions``. Prompt *text* is source-resident and git-versioned
(:mod:`qe_prompt_registry.templates`); the table mirrors it and carries the §19
lifecycle state.

This package does not import :mod:`qe_ai_gateway`, and the gateway does not
import this one — the gateway receives a resolved version string as a parameter
(ADR-0209 Decision 5).
"""

from __future__ import annotations

from qe_common.prompts import PromptStatus
from qe_prompt_registry.seed import PATH_TO_ACTIVE, SeedOutcome, seed_all, seed_template
from qe_prompt_registry.service import (
    create_version,
    get_active,
    get_version,
    list_versions,
    transition_status,
)
from qe_prompt_registry.templates import (
    SOURCE_TEMPLATES,
    SourceTemplate,
    get_source_template,
    sha256_of,
)

__all__ = [
    "PATH_TO_ACTIVE",
    "SOURCE_TEMPLATES",
    "PromptStatus",
    "SeedOutcome",
    "SourceTemplate",
    "create_version",
    "get_active",
    "get_source_template",
    "get_version",
    "list_versions",
    "seed_all",
    "seed_template",
    "sha256_of",
    "transition_status",
]
