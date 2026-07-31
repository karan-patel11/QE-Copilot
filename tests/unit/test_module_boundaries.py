"""N3+N4 unit: the module boundaries ADR-0209 claims are mechanically checkable.

§37 L2745 forbids provider calls outside the gateway and §12.2 forbids one
module querying another's tables. Both are the kind of rule that decays silently
unless something fails when it is broken, so it is asserted here rather than
left as prose in an ADR.
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

VENDOR_MODULES = {"anthropic", "openai", "cohere", "mistralai", "google"}


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
    """``import qe_ai_gateway`` must not drag in ``anthropic``.

    The deterministic tier runs on MockProvider with no credential; if importing
    the package pulled in the SDK, that tier would depend on a vendor library it
    never calls. Checked in a fresh interpreter because another test in this
    process may already have imported ``anthropic``.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import qe_ai_gateway; " "sys.exit(1 if 'anthropic' in sys.modules else 0)",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "importing qe_ai_gateway pulled in the anthropic SDK.\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )


@pytest.mark.parametrize("module", ["qe_ai_gateway", "qe_prompt_registry"])
def test_packages_import_cleanly(module: str) -> None:
    __import__(module)
