"""The §22.2 validation chain, levels 1-6 (ADR-0205, ADR-0211).

Every check reports under its own :class:`~qe_common.test_generation.ValidationCheck`
name, so a failure is always attributable to the level that caught it rather than
collapsing into a generic "invalid". That attribution is the point: the
``validation_errors`` corpus is the evidence base for what a future sandbox would
need to catch.

**Nothing here executes generated code.** ``ast.parse`` builds a tree and stops;
there is no ``exec``, no ``eval``, and no ``compile`` to a callable anywhere in
this module. §23 L1991 forbids executing generated code in the API or worker
container, and this phase satisfies that the simplest way available — by
executing it nowhere at all.

Level 7 (sandbox execution) is deferred: §22.2 L1983 marks it optional, §39 L2910
makes it P1, and §38 L2802 scopes this phase to static validation.
"""

from __future__ import annotations

import ast
import difflib
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from qe_common.test_generation import ValidationCheck
from qe_test_generation.contracts import GeneratedCase

#: Level 4. Standard-library modules a generated Pytest file may import, plus
#: ``pytest`` itself. Deliberately short: a generated test that needs anything
#: beyond this is reaching outside what a requirement can justify.
ALLOWED_IMPORT_ROOTS: frozenset[str] = frozenset(
    {
        "pytest",
        "unittest",
        "abc",
        "collections",
        "contextlib",
        "copy",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "fractions",
        "functools",
        "itertools",
        "json",
        "math",
        "operator",
        "random",
        "re",
        "statistics",
        "string",
        "textwrap",
        "types",
        "typing",
        "uuid",
    }
)

#: Level 6. Modules whose presence is a safety finding rather than merely an
#: allowlist miss. Derived from §23's sandbox threat model — no secrets, no
#: metadata services, network disabled — applied statically (ADR-0205).
UNSAFE_IMPORT_ROOTS: frozenset[str] = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "shutil",
        "socket",
        "requests",
        "httpx",
        "urllib",
        "http",
        "ftplib",
        "smtplib",
        "paramiko",
        "pickle",
        "marshal",
        "ctypes",
        "multiprocessing",
        "importlib",
        "pty",
        "webbrowser",
    }
)

#: Level 6. Bare calls that hand control to a string.
UNSAFE_BUILTINS: frozenset[str] = frozenset({"eval", "exec", "compile", "__import__", "breakpoint"})

#: Level 6. ``module.attribute`` calls that act on the host.
UNSAFE_ATTRIBUTE_CALLS: frozenset[str] = frozenset(
    {
        "os.system",
        "os.popen",
        "os.remove",
        "os.unlink",
        "os.rmdir",
        "os.execv",
        "os.fork",
        "shutil.rmtree",
        "shutil.move",
        "subprocess.run",
        "subprocess.call",
        "subprocess.Popen",
        "subprocess.check_output",
        "socket.socket",
        "requests.get",
        "requests.post",
        "importlib.import_module",
    }
)

#: Level 6. Credential-shaped literals. Patterns rather than entropy alone, since
#: a short real key beats a long random-looking placeholder for damage done.
_CREDENTIAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("AWS access key id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}")),
    ("bearer token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{20,}")),
    (
        "database connection string with credentials",
        re.compile(r"(?i)\b(postgres|postgresql|mysql|mongodb)(\+\w+)?://[^\s'\"]+:[^\s'\"]+@"),
    ),
    (
        "inline credential assignment",
        re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token)\s*[=:]\s*.{6,}"),
    ),
)

#: Level 5. Above this similarity two cases are the same test written twice.
#: Tuned to catch rewording, not to merge genuinely different boundary cases.
DUPLICATE_THRESHOLD = 0.85

_WHITESPACE = re.compile(r"\s+")

#: Level 2. Fields that must carry content for a case to be reviewable at all.
REQUIRED_CASE_FIELDS: tuple[str, ...] = (
    "title",
    "objective",
    "steps",
    "expected_result",
    "priority",
)


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    """One failed check, named by the level that caught it."""

    check: ValidationCheck
    message: str

    def as_dict(self) -> dict[str, str]:
        """The ``validation_errors`` JSONB shape: ``{check, message}``."""
        return {"check": self.check.value, "message": self.message}


@dataclass(slots=True)
class CaseValidation:
    """The chain's verdict on one case."""

    findings: list[ValidationFinding] = field(default_factory=list)
    #: Ordinal of the earlier case this duplicates, if any.
    duplicate_of_ordinal: int | None = None
    duplicate_score: float | None = None

    def checks_failed(self) -> set[ValidationCheck]:
        return {finding.check for finding in self.findings}

    @property
    def schema_valid(self) -> bool:
        """§15.6's first boolean — levels 1 and 2, the structured payload."""
        return not self.checks_failed() & {
            ValidationCheck.SCHEMA,
            ValidationCheck.REQUIRED_FIELDS,
        }

    @property
    def syntax_valid(self) -> bool:
        """§15.6's second boolean — levels 3, 4 and 6, the code itself.

        Safety is folded in here deliberately. §15.6 specifies exactly two
        booleans and no migration adds a third, but a case carrying an unsafe
        construct must not read as ``PASSED`` through
        :attr:`~qe_database.models.GeneratedTestCase.validation_status`. So this
        boolean means "the code is statically acceptable" — it parses, its
        imports are permitted, and it contains nothing unsafe — and the specific
        level that failed is never lost, because it is named in
        ``validation_errors``.
        """
        return not self.checks_failed() & {
            ValidationCheck.SYNTAX,
            ValidationCheck.IMPORTS,
            ValidationCheck.SAFETY,
        }

    @property
    def is_duplicate(self) -> bool:
        return self.duplicate_of_ordinal is not None


def check_schema(payload: Any, model: type[BaseModel]) -> list[ValidationFinding]:
    """Level 1 — JSON/schema validation (§22.2 L1977).

    The gateway already validates against this model, so a payload arriving here
    normally passes. It is re-checked because the level exists to be *reported*:
    a case persisted with ``schema_valid`` true should mean a check ran, not that
    an earlier layer probably did one.
    """
    try:
        model.model_validate(payload)
    except ValidationError as exc:
        return [
            ValidationFinding(
                ValidationCheck.SCHEMA,
                f"{'.'.join(str(p) for p in error['loc']) or model.__name__}: {error['msg']}",
            )
            for error in exc.errors()
        ]
    return []


def check_required_fields(case: GeneratedCase, code: str) -> list[ValidationFinding]:
    """Level 2 — required-field validation (§22.2 L1978)."""
    findings: list[ValidationFinding] = []
    for name in REQUIRED_CASE_FIELDS:
        value = getattr(case, name, None)
        if value is None or (isinstance(value, str | list) and len(value) == 0):
            findings.append(ValidationFinding(ValidationCheck.REQUIRED_FIELDS, f"{name} is empty."))
    if not code.strip():
        findings.append(
            ValidationFinding(ValidationCheck.REQUIRED_FIELDS, "generated_code is empty.")
        )
    return findings


def check_syntax(code: str) -> tuple[list[ValidationFinding], ast.Module | None]:
    """Level 3 — framework syntax validation (§22.2 L1979).

    ``ast.parse`` only builds a tree. It does not execute, import, or evaluate
    anything the code names, so parsing hostile source is safe.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [
            ValidationFinding(
                ValidationCheck.SYNTAX,
                f"line {exc.lineno}: {exc.msg}",
            )
        ], None
    return [], tree


def _imported_roots(tree: ast.Module) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def check_imports(tree: ast.Module) -> list[ValidationFinding]:
    """Level 4 — import validation (§22.2 L1980)."""
    return [
        ValidationFinding(
            ValidationCheck.IMPORTS,
            f"import of {root!r} is not on the allowlist for generated tests.",
        )
        for root in sorted(_imported_roots(tree) - ALLOWED_IMPORT_ROOTS)
    ]


def _dotted_name(node: ast.expr) -> str | None:
    """Render ``a.b.c`` from an attribute/name chain, or ``None``."""
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return ".".join(reversed(parts))


def check_safety(tree: ast.Module, code: str) -> list[ValidationFinding]:
    """Level 6 — safety scanning (§22.2 L1982).

    Flags; never silently strips. A case whose code is rewritten behind the
    reviewer's back would present as clean while hiding what the model actually
    produced, which defeats the review §8.2 exists to guarantee.
    """
    findings: list[ValidationFinding] = []

    for root in sorted(_imported_roots(tree) & UNSAFE_IMPORT_ROOTS):
        findings.append(
            ValidationFinding(
                ValidationCheck.SAFETY,
                f"imports {root!r}, which can reach the host, the network, or the filesystem.",
            )
        )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in UNSAFE_BUILTINS:
            findings.append(
                ValidationFinding(
                    ValidationCheck.SAFETY,
                    f"calls {node.func.id}(), which executes code built at runtime.",
                )
            )
            continue
        dotted = _dotted_name(node.func)
        if dotted in UNSAFE_ATTRIBUTE_CALLS:
            findings.append(ValidationFinding(ValidationCheck.SAFETY, f"calls {dotted}()."))
        elif isinstance(node.func, ast.Name) and node.func.id == "open":
            mode = _open_mode(node)
            if mode is not None and any(flag in mode for flag in ("w", "a", "x", "+")):
                findings.append(
                    ValidationFinding(
                        ValidationCheck.SAFETY,
                        f"opens a file for writing (mode {mode!r}).",
                    )
                )

    for label, pattern in _CREDENTIAL_PATTERNS:
        if pattern.search(code):
            findings.append(
                ValidationFinding(
                    ValidationCheck.SAFETY,
                    f"contains what looks like a {label}; generated tests must not embed "
                    "credentials, real or placeholder.",
                )
            )

    return findings


def _open_mode(node: ast.Call) -> str | None:
    """The literal mode argument of an ``open()`` call, if it has one."""
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
        value = node.args[1].value
        return value if isinstance(value, str) else None
    for keyword in node.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            value = keyword.value.value
            return value if isinstance(value, str) else None
    return None


def case_signature(case: GeneratedCase) -> str:
    """Normalised text used for similarity. Title, objective, and step actions."""
    parts = [case.title, case.objective, *(step.action for step in case.steps)]
    return _WHITESPACE.sub(" ", " ".join(parts)).strip().lower()


def check_duplicate(
    case: GeneratedCase,
    earlier: list[GeneratedCase],
    *,
    threshold: float = DUPLICATE_THRESHOLD,
) -> tuple[list[ValidationFinding], int | None, float | None]:
    """Level 5 — duplicate detection (§22.2 L1981), within one request.

    A duplicate is **not** invalid: it is a real test that happens to already
    exist, so it is recorded with its score and its counterpart and left for the
    reviewer. Only ``duplicate_score`` and ``duplicate_of`` change; the two
    validity booleans do not.
    """
    if not earlier:
        return [], None, None

    signature = case_signature(case)
    best_ordinal: int | None = None
    best_score = 0.0
    for ordinal, other in enumerate(earlier):
        score = difflib.SequenceMatcher(None, signature, case_signature(other)).ratio()
        if score > best_score:
            best_score, best_ordinal = score, ordinal

    if best_ordinal is None or best_score < threshold:
        return [], None, round(best_score, 4) if earlier else None

    return (
        [
            ValidationFinding(
                ValidationCheck.DUPLICATE,
                f"duplicates case #{best_ordinal} (similarity {best_score:.2f}).",
            )
        ],
        best_ordinal,
        round(best_score, 4),
    )


def validate_case(
    case: GeneratedCase,
    code: str,
    earlier: list[GeneratedCase],
    *,
    payload: Any | None = None,
) -> CaseValidation:
    """Run levels 1-6 in §22.2's order and collect every finding.

    The chain does not short-circuit. A case with a syntax error is still checked
    for duplicates and credentials, because a reviewer fixing one problem should
    see all of them rather than rediscovering the next on the following pass.
    """
    result = CaseValidation()

    result.findings.extend(check_schema(payload if payload is not None else case, GeneratedCase))
    result.findings.extend(check_required_fields(case, code))

    syntax_findings, tree = check_syntax(code)
    result.findings.extend(syntax_findings)

    if tree is not None:
        result.findings.extend(check_imports(tree))

    duplicate_findings, duplicate_of, score = check_duplicate(case, earlier)
    result.findings.extend(duplicate_findings)
    result.duplicate_of_ordinal = duplicate_of
    result.duplicate_score = score

    if tree is not None:
        result.findings.extend(check_safety(tree, code))
    else:
        # The tree is unavailable, so only the textual half of level 6 can run.
        # Reported rather than skipped silently: an unparseable file is exactly
        # where a credential is most likely to go unnoticed.
        for label, pattern in _CREDENTIAL_PATTERNS:
            if pattern.search(code):
                result.findings.append(
                    ValidationFinding(
                        ValidationCheck.SAFETY,
                        f"contains what looks like a {label} (text scan only — the code "
                        "did not parse, so construct scanning could not run).",
                    )
                )

    return result


__all__ = [
    "ALLOWED_IMPORT_ROOTS",
    "DUPLICATE_THRESHOLD",
    "REQUIRED_CASE_FIELDS",
    "UNSAFE_ATTRIBUTE_CALLS",
    "UNSAFE_BUILTINS",
    "UNSAFE_IMPORT_ROOTS",
    "CaseValidation",
    "ValidationFinding",
    "case_signature",
    "check_duplicate",
    "check_imports",
    "check_required_fields",
    "check_safety",
    "check_schema",
    "check_syntax",
    "validate_case",
]
