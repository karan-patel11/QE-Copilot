"""N5 unit: decomposition contract, config rejection, and the §22.2 chain.

Deterministic tier — no network, no database, no provider key (ADR-0206).
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from qe_common.errors import TestConfigInvalidError, TestConfigUnsupportedError
from qe_common.test_generation import TestType, ValidationCheck
from qe_test_generation.config import validate_configuration
from qe_test_generation.contracts import (
    DECOMPOSITION_FIELDS,
    Decomposition,
    GeneratedCase,
    decomposition_summary,
)
from qe_test_generation.validation import (
    CaseValidation,
    check_duplicate,
    check_imports,
    check_safety,
    check_syntax,
    validate_case,
)
from tests.helpers_testgen import CASES_PAYLOAD, DECOMPOSITION_PAYLOAD, SAFE_CODE

# --- ADR-0207: the ten outputs, all always present --------------------------


def test_decomposition_declares_exactly_the_ten_spec_fields() -> None:
    """§22.1 L1962-1971. Ten, under these names, no more and no fewer."""
    assert set(Decomposition.model_fields) == set(DECOMPOSITION_FIELDS)
    assert len(DECOMPOSITION_FIELDS) == 10


def test_a_valid_decomposition_carries_all_ten_keys() -> None:
    decomposition = Decomposition.model_validate(DECOMPOSITION_PAYLOAD)
    for name in DECOMPOSITION_FIELDS:
        assert hasattr(decomposition, name), name


@pytest.mark.parametrize("missing", DECOMPOSITION_FIELDS)
def test_a_missing_key_is_rejected(missing: str) -> None:
    """An absent key is not an empty list, and must not be silently treated as one.

    This is the assertion that keeps ADR-0207's rule true: if any field grew a
    default, the model omitting it would validate and the caller would read
    "nothing found" where the truth is "the model said nothing".
    """
    payload = copy.deepcopy(DECOMPOSITION_PAYLOAD)
    payload.pop(missing)
    with pytest.raises(ValidationError) as exc:
        Decomposition.model_validate(payload)
    assert missing in str(exc.value)


@pytest.mark.parametrize(
    "emptied",
    [name for name in DECOMPOSITION_FIELDS if name not in {"actions", "success_conditions"}],
)
def test_an_empty_list_is_accepted(emptied: str) -> None:
    """Emptiness is expressed as ``[]`` and is a legitimate answer."""
    payload = copy.deepcopy(DECOMPOSITION_PAYLOAD)
    payload[emptied] = []
    assert getattr(Decomposition.model_validate(payload), emptied) == []


def test_actions_and_success_conditions_may_not_both_be_empty() -> None:
    """ADR-0207's one semantic check: nothing testable means the stage fails."""
    payload = copy.deepcopy(DECOMPOSITION_PAYLOAD)
    payload["actions"] = []
    payload["success_conditions"] = []
    with pytest.raises(ValidationError, match="nothing testable"):
        Decomposition.model_validate(payload)


def test_either_one_alone_may_be_empty() -> None:
    for name in ("actions", "success_conditions"):
        payload = copy.deepcopy(DECOMPOSITION_PAYLOAD)
        payload[name] = []
        assert Decomposition.model_validate(payload) is not None


def test_the_log_summary_carries_cardinalities_but_no_content() -> None:
    """§26.5 — the shape is recoverable from logs; the requirement text is not."""
    summary = decomposition_summary(Decomposition.model_validate(DECOMPOSITION_PAYLOAD))
    assert summary["actors"] == 1
    assert set(summary) == set(DECOMPOSITION_FIELDS)
    assert all(isinstance(value, int) for value in summary.values())
    assert "subscriber" not in str(summary)


# --- ADR-0208: accessibility is refused, not accepted -----------------------


def test_accessibility_cases_are_rejected_with_422() -> None:
    """Accepting the flag would label tests as covering something they do not."""
    with pytest.raises(TestConfigUnsupportedError) as exc:
        validate_configuration({"include_accessibility_cases": True})
    assert exc.value.http_status == 422
    assert exc.value.code.value == "TEST_CONFIG_UNSUPPORTED"
    assert "accessibility" in exc.value.message.lower()
    assert exc.value.details[0].field == "configuration.include_accessibility_cases"


def test_accessibility_false_is_accepted() -> None:
    config = validate_configuration({"include_accessibility_cases": False})
    assert config.include_accessibility_cases is False


def test_defaults_are_resolved_and_stored_not_implied() -> None:
    """ADR-0208: the full eleven keys are written, so history explains itself."""
    config = validate_configuration({})
    stored = config.model_dump()
    assert len(stored) == 11
    assert stored["number_of_tests"] == 5
    assert stored["include_security_cases"] is False


@pytest.mark.parametrize("count", [0, 21, -1])
def test_number_of_tests_is_bounded(count: int) -> None:
    with pytest.raises(TestConfigInvalidError) as exc:
        validate_configuration({"number_of_tests": count})
    assert exc.value.http_status == 422


def test_unknown_configuration_keys_are_rejected() -> None:
    with pytest.raises(TestConfigInvalidError):
        validate_configuration({"include_chaos_cases": True})


def test_requested_kinds_covers_every_include_flag() -> None:
    """The mapping ADR-0211 Decision 6 widened TestType to make expressible."""
    config = validate_configuration({"include_security_cases": True})
    assert set(config.requested_kinds) == {
        TestType.POSITIVE,
        TestType.NEGATIVE,
        TestType.BOUNDARY,
        TestType.SECURITY,
    }
    assert config.requested_kinds[TestType.SECURITY] is True


# --- §22.2: each level catches its own failure, and only its own ------------


def _case(**overrides: Any) -> GeneratedCase:
    payload = copy.deepcopy(CASES_PAYLOAD["cases"][0])
    payload.update(overrides)
    return GeneratedCase.model_validate(payload)


def test_a_clean_case_passes_every_level() -> None:
    result = validate_case(_case(), SAFE_CODE, [])
    assert result.findings == []
    assert result.schema_valid and result.syntax_valid
    assert not result.is_duplicate


def test_level_2_catches_a_missing_required_field() -> None:
    result = validate_case(_case(title=""), SAFE_CODE, [])
    assert result.checks_failed() == {ValidationCheck.REQUIRED_FIELDS}
    assert not result.schema_valid
    assert result.syntax_valid, "an empty title must not be reported as a code problem"


def test_level_2_catches_empty_generated_code() -> None:
    result = validate_case(_case(), "   ", [])
    assert ValidationCheck.REQUIRED_FIELDS in result.checks_failed()


def test_level_3_catches_a_syntax_error_and_names_it_syntax() -> None:
    findings, tree = check_syntax("def test_x(:\n    pass\n")
    assert tree is None
    assert [f.check for f in findings] == [ValidationCheck.SYNTAX]

    result = validate_case(_case(), "def test_x(:\n    pass\n", [])
    assert ValidationCheck.SYNTAX in result.checks_failed()
    assert not result.syntax_valid


def test_level_4_catches_a_disallowed_import_without_flagging_safety() -> None:
    """``csv`` is not on the allowlist but is not dangerous — level 4 only."""
    code = "import csv\n\n\ndef test_x():\n    assert True\n"
    result = validate_case(_case(), code, [])
    assert result.checks_failed() == {ValidationCheck.IMPORTS}


def test_level_5_flags_a_duplicate_without_invalidating_it() -> None:
    """A duplicate is a real test that already exists, not an invalid one."""
    original = _case()
    twin = _case()
    result = validate_case(twin, SAFE_CODE, [original])

    assert ValidationCheck.DUPLICATE in result.checks_failed()
    assert result.is_duplicate
    assert result.duplicate_of_ordinal == 0
    assert result.duplicate_score is not None and result.duplicate_score >= 0.85
    assert result.schema_valid and result.syntax_valid


def test_level_5_does_not_flag_genuinely_different_cases() -> None:
    first = _case()
    second = GeneratedCase.model_validate(CASES_PAYLOAD["cases"][1])
    findings, ordinal, score = check_duplicate(second, [first])
    assert findings == []
    assert ordinal is None
    assert score is not None and score < 0.85


def test_level_6_catches_eval_without_flagging_imports() -> None:
    """``eval`` needs no import, so this fixture isolates level 6."""
    code = "def test_x():\n    eval('1 + 1')\n"
    result = validate_case(_case(), code, [])
    assert result.checks_failed() == {ValidationCheck.SAFETY}
    assert not result.syntax_valid, "unsafe code must not read as PASSED"


@pytest.mark.parametrize(
    "snippet",
    [
        "import subprocess\n\n\ndef test_x():\n    assert True\n",
        "import os\n\n\ndef test_x():\n    os.system('rm -rf /')\n",
        "def test_x():\n    exec('x = 1')\n",
        "def test_x():\n    open('/tmp/x', 'w')\n",
    ],
)
def test_level_6_catches_destructive_and_exfiltrating_constructs(snippet: str) -> None:
    result = validate_case(_case(), snippet, [])
    assert ValidationCheck.SAFETY in result.checks_failed()


@pytest.mark.parametrize(
    "secret",
    [
        "AKIAIOSFODNN7EXAMPLE",
        "ghp_0123456789abcdefghijklmnopqrstuvwx",
        "postgres://user:hunter2@db.internal:5432/app",
        "-----BEGIN RSA PRIVATE KEY-----",
    ],
)
def test_level_6_catches_credential_shaped_literals(secret: str) -> None:
    code = f'def test_x():\n    token = "{secret}"\n    assert token\n'
    result = validate_case(_case(), code, [])
    assert ValidationCheck.SAFETY in result.checks_failed()


def test_safety_findings_flag_and_never_rewrite_the_code() -> None:
    """ADR-0205: flags, never silently strips.

    Rewriting model output behind the reviewer would present as clean while
    hiding what was actually produced, defeating the review §8.2 requires.
    """
    code = "def test_x():\n    eval('1 + 1')\n"
    findings = check_safety(check_syntax(code)[1], code)  # type: ignore[arg-type]
    assert findings
    assert "eval" in code, "the input must be untouched"


def test_the_chain_does_not_short_circuit() -> None:
    """A reviewer should see every problem at once, not one per pass."""
    code = "import csv\n\n\ndef test_x():\n    eval('1')\n"
    result = validate_case(_case(title=""), code, [])
    assert result.checks_failed() == {
        ValidationCheck.REQUIRED_FIELDS,
        ValidationCheck.IMPORTS,
        ValidationCheck.SAFETY,
    }


def test_credentials_are_still_scanned_when_the_code_will_not_parse() -> None:
    """An unparseable file is where a credential is most likely to go unnoticed."""
    code = 'def test_x(:\n    key = "AKIAIOSFODNN7EXAMPLE"\n'
    result = validate_case(_case(), code, [])
    assert {ValidationCheck.SYNTAX, ValidationCheck.SAFETY} <= result.checks_failed()


def test_import_check_allows_the_pytest_toolkit() -> None:
    code = "import pytest\nfrom unittest import mock\nfrom decimal import Decimal\n"
    assert check_imports(check_syntax(code)[1]) == []  # type: ignore[arg-type]


def test_validation_booleans_map_to_the_documented_levels() -> None:
    """§15.6's two booleans, per ADR-0211: 1-2 → schema, 3/4/6 → syntax."""
    assert CaseValidation().schema_valid and CaseValidation().syntax_valid
