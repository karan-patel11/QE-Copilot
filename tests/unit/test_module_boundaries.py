"""N3+N4+N5 unit: the module boundaries the ADRs claim are mechanically checkable.

§37 L2745 forbids provider calls outside the gateway. ADR-0209 Decision 5 adds a
stricter no-cross-module-queries rule as *our* design decision — §12.2 L1110's
own words forbid modules *modifying* another module's records through
uncontrolled queries, and this codebase declines cross-module reads too.

ADR-0211 Decision 1 adds a third: exactly one event loop per generation.

All of these decay silently unless something fails when they are broken, so they
are asserted here rather than left as prose in an ADR.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE_ROOTS = (REPO_ROOT / "packages", REPO_ROOT / "apps")

#: Only this package may import a vendor SDK (§18 L1766, §37 L2745).
GATEWAY_PACKAGE = REPO_ROOT / "packages" / "ai_gateway"

VENDOR_MODULES = {"groq", "anthropic", "openai", "cohere", "mistralai", "google"}

#: The SDK the gateway is allowed to import (ADR-0210). ``anthropic`` stays in
#: VENDOR_MODULES above so its reintroduction anywhere fails loudly.
CURRENT_VENDOR_SDK = "groq"

#: Removed by ADR-0210. Checked as *uninstallable*, not merely unimported — an
#: unused-but-present dependency still ships, still needs patching, and would let
#: an import of it silently start working again.
REMOVED_VENDOR_SDKS = ("anthropic",)


def _python_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for root in SOURCE_ROOTS:
        if not root.exists():
            continue
        files.extend(
            path
            for path in root.rglob("*.py")
            if ".venv" not in path.parts and "node_modules" not in path.parts
        )
    return files


def _imported_roots(path: pathlib.Path) -> set[str]:
    """Top-level module names imported by ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_only_the_gateway_imports_a_provider_sdk() -> None:
    offenders: list[str] = []
    for path in _python_files():
        if GATEWAY_PACKAGE in path.parents:
            continue
        leaked = _imported_roots(path) & VENDOR_MODULES
        if leaked:
            offenders.append(f"{path.relative_to(REPO_ROOT)}: {sorted(leaked)}")
    assert not offenders, "provider SDK imported outside packages/ai_gateway:\n" + "\n".join(
        offenders
    )


def test_gateway_does_not_import_the_prompt_registry() -> None:
    """The boundary that keeps the gateway unable to invent a version string.

    If the gateway could read ``prompt_versions`` it could also construct a
    plausible-looking ``prompt_version_id``, and the future foreign-key backfill
    (ADR-0209 Decision 2) would have no way to tell an invented string from a
    real one.
    """
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in GATEWAY_PACKAGE.rglob("*.py")
        if "qe_prompt_registry" in _imported_roots(path)
    ]
    assert not offenders, f"ai_gateway must not import the prompt registry: {offenders}"


def test_prompt_registry_does_not_import_the_gateway() -> None:
    """The other direction — together these two make a cycle impossible."""
    registry = REPO_ROOT / "packages" / "prompt_registry"
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in registry.rglob("*.py")
        if "qe_ai_gateway" in _imported_roots(path)
    ]
    assert not offenders, f"prompt_registry must not import the gateway: {offenders}"


def test_gateway_package_import_does_not_pull_in_the_vendor_sdk() -> None:
    """``import qe_ai_gateway`` must not drag in ``groq``.

    The deterministic tier runs on MockProvider with no credential; if importing
    the package pulled in the SDK, that tier would depend on a vendor library it
    never calls. Checked in a fresh interpreter because another test in this
    process may already have imported ``groq``.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import qe_ai_gateway; "
            f"sys.exit(1 if {CURRENT_VENDOR_SDK!r} in sys.modules else 0)",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"importing qe_ai_gateway pulled in the {CURRENT_VENDOR_SDK} SDK.\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )


@pytest.mark.parametrize("sdk", REMOVED_VENDOR_SDKS)
def test_removed_vendor_sdk_is_gone_from_the_dependency_tree(sdk: str) -> None:
    """A replaced SDK must be uninstalled, not just unimported (ADR-0210).

    Leaving it installed keeps it in the shipped image and its CVE surface, and
    lets a stray ``import anthropic`` start working again with nothing failing.
    """
    declared = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'"{sdk}==' not in declared, f"{sdk} is still declared in pyproject.toml"

    result = subprocess.run(
        [sys.executable, "-c", f"import {sdk}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (
        result.returncode != 0
    ), f"{sdk} is still importable — it must be uninstalled, not merely unused."


@pytest.mark.parametrize("module", ["qe_ai_gateway", "qe_prompt_registry", "qe_test_generation"])
def test_packages_import_cleanly(module: str) -> None:
    __import__(module)


# --- ADR-0211 Decision 1: one event loop per generation ---------------------

TEST_GENERATION_PACKAGE = REPO_ROOT / "packages" / "test_generation"

#: Every way of standing up or entering an event loop. A second one anywhere in
#: this package would mean a provider call ran on its own loop.
_LOOP_ENTRY_POINTS = {
    ("asyncio", "run"),
    ("asyncio", "new_event_loop"),
    ("asyncio", "set_event_loop"),
    ("asyncio", "get_event_loop"),
    ("loop", "run_until_complete"),
}

#: The one module allowed to open a loop — the documented bridge.
_BRIDGE_MODULE = "pipeline.py"


def _loop_entry_calls(path: pathlib.Path) -> list[str]:
    """Dotted names of any event-loop entry points called in ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner = node.func.value
        if isinstance(owner, ast.Name) and (owner.id, node.func.attr) in _LOOP_ENTRY_POINTS:
            found.append(f"{owner.id}.{node.func.attr}")
    return found


def test_exactly_one_event_loop_is_opened_in_the_pipeline() -> None:
    """The sync/async bridge happens once, at the pipeline entry point.

    A per-provider-call ``asyncio.run`` would create and tear down a loop for
    every call, discard the client state held between them, and serialise work
    the pipeline could otherwise overlap — the failure ADR-0211 Decision 1 exists
    to prevent, and one that no functional test would notice.
    """
    offenders: dict[str, list[str]] = {}
    total = 0
    for path in sorted(TEST_GENERATION_PACKAGE.rglob("*.py")):
        calls = _loop_entry_calls(path)
        if not calls:
            continue
        total += len(calls)
        if path.name != _BRIDGE_MODULE:
            offenders[str(path.relative_to(REPO_ROOT))] = calls

    assert (
        not offenders
    ), f"event loops may only be opened in {_BRIDGE_MODULE}, but found: {offenders}"
    assert total == 1, (
        f"expected exactly one event-loop entry point in the package, found {total}. "
        "The bridge is a single asyncio.run at the Celery task boundary (ADR-0211 D1)."
    )


def test_test_generation_does_not_import_a_provider_sdk() -> None:
    """N5 calls the gateway interface only (§18 L1766, §37 L2745)."""
    offenders = [
        f"{path.relative_to(REPO_ROOT)}: {sorted(_imported_roots(path) & VENDOR_MODULES)}"
        for path in TEST_GENERATION_PACKAGE.rglob("*.py")
        if _imported_roots(path) & VENDOR_MODULES
    ]
    assert not offenders, f"test_generation must not import a provider SDK: {offenders}"
