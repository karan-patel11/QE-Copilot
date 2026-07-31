"""Shared N5 fixtures — deterministic payloads for the MockProvider tier.

Every payload here is a *valid* stage response. Tests that need an invalid one
mutate a copy, so the thing under test is always the single field that changed
(ADR-0206: exact assertions, because with a stubbed provider the system is fully
deterministic).
"""

from __future__ import annotations

from typing import Any

from qe_common.ai import ModelOperation
from qe_prompt_registry.templates import SOURCE_TEMPLATES
from qe_test_generation.stages import PROMPT_NAMES, ResolvedPrompt

#: §40's demo requirement, so the fixture is the one the spec itself uses.
REQUIREMENT = "A subscriber should be able to resume playback on another registered device."

DECOMPOSITION_PAYLOAD: dict[str, Any] = {
    "actors": ["subscriber"],
    "preconditions": ["the subscriber has an active subscription"],
    "actions": ["resume playback on another registered device"],
    "business_rules": ["playback resumes at the last known position"],
    "state_transitions": [{"from": "paused", "to": "playing", "trigger": "resume requested"}],
    "success_conditions": ["playback resumes at the stored position"],
    "failure_conditions": ["the entitlement token has expired"],
    "data_constraints": [{"field": "device_id", "constraint": "must be registered"}],
    "security_constraints": ["entitlement is validated per device"],
    "integration_dependencies": ["entitlement service"],
}

PLAN_PAYLOAD: dict[str, Any] = {
    "cases": [
        {
            "title": "Resume playback on a second registered device",
            "objective": "Playback resumes at the stored position",
            "test_type": "positive",
            "priority": "P1",
            "covers": "success_conditions[0]",
        },
        {
            "title": "Reject resume when the entitlement token has expired",
            "objective": "An expired entitlement stops playback resuming",
            "test_type": "negative",
            "priority": "P1",
            "covers": "failure_conditions[0]",
        },
    ],
    "coverage_notes": "No boundary cases: the requirement states no numeric limits.",
}

SAFE_CODE = "import pytest\n\n\ndef test_resume_playback():\n    assert True\n"


def _case(title: str, objective: str, test_type: str) -> dict[str, Any]:
    return {
        "title": title,
        "objective": objective,
        "preconditions": "The subscriber has an active subscription.",
        "test_data": [{"name": "device_id", "value": "device-2"}],
        "steps": [{"action": "Request resume on device 2", "expected": "Playback starts"}],
        "expected_result": "Playback resumes at the stored position",
        "priority": "P1",
        "tags": ["playback"],
        "test_type": test_type,
    }


CASES_PAYLOAD: dict[str, Any] = {
    "cases": [
        _case(
            "Resume playback on a second registered device",
            "Playback resumes at the stored position",
            "positive",
        ),
        _case(
            "Reject resume when the entitlement token has expired",
            "An expired entitlement stops playback resuming",
            "negative",
        ),
    ]
}

CODE_PAYLOAD: dict[str, Any] = {
    "items": [
        {"title": "Resume playback on a second registered device", "code": SAFE_CODE},
        {"title": "Reject resume when the entitlement token has expired", "code": SAFE_CODE},
    ]
}

#: The four stage responses in pipeline order — what MockProvider replays.
STAGE_RESPONSES: list[dict[str, Any]] = [
    DECOMPOSITION_PAYLOAD,
    PLAN_PAYLOAD,
    CASES_PAYLOAD,
    CODE_PAYLOAD,
]


def source_prompts() -> dict[ModelOperation, ResolvedPrompt]:
    """Resolve prompts straight from source, with no database.

    The registry path (``resolve_prompts``) is exercised against a real database
    in the integration tier; the deterministic tier only needs the templates.
    """
    resolved: dict[ModelOperation, ResolvedPrompt] = {}
    for operation, prompt_name in PROMPT_NAMES.items():
        template = SOURCE_TEMPLATES[f"{prompt_name}-v1"]
        resolved[operation] = ResolvedPrompt(version=template.version, template=template)
    return resolved


__all__ = [
    "CASES_PAYLOAD",
    "CODE_PAYLOAD",
    "DECOMPOSITION_PAYLOAD",
    "PLAN_PAYLOAD",
    "REQUIREMENT",
    "SAFE_CODE",
    "STAGE_RESPONSES",
    "source_prompts",
]
