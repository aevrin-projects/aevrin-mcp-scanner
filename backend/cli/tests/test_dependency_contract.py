"""Guards the CLI's declared floor on aevrin-scanner-core.

Why this exists: the CLI resolves scanner-core from PyPI for real users, but
from an editable workspace path during development (see `[tool.uv.sources]`).
That means a CLI importing a scanner-core symbol *newer* than its declared
minimum works perfectly on every developer machine and in CI, then dies with
an ImportError on a real `pipx install aevrin`.

That exact bug shipped once: `output.py` began importing `is_autofix_eligible`
while `pyproject.toml` still declared `aevrin-scanner-core>=0.1.8`, a version
that predates the symbol. These tests fail loudly instead.
"""

from __future__ import annotations

import ast
import pathlib
import re

CLI_ROOT = pathlib.Path(__file__).resolve().parents[1]
# Sibling, matching the `../scanner-core` uv source in pyproject.toml, so this
# keeps working if the tree is rearranged again.
SCANNER_CORE = CLI_ROOT.parent / "scanner-core"


def _declared_floor() -> tuple[int, ...]:
    text = (CLI_ROOT / "pyproject.toml").read_text()
    match = re.search(r'"aevrin-scanner-core>=([0-9.]+)"', text)
    assert match, "CLI must declare an explicit aevrin-scanner-core floor"
    return tuple(int(part) for part in match.group(1).split("."))


def _scanner_core_version() -> tuple[int, ...]:
    text = (SCANNER_CORE / "pyproject.toml").read_text()
    match = re.search(r'^version = "([0-9.]+)"', text, re.MULTILINE)
    assert match, "scanner-core must declare a version"
    return tuple(int(part) for part in match.group(1).split("."))


def _symbols_imported_from_scanner_core() -> set[tuple[str, str]]:
    """(module, name) for every scanner-core import in the CLI.

    Keyed by the *originating module*, not just the name, the CLI imports
    from submodules too (`aevrin_scanner_core.pipeline`,
    `.network_safety`), and those symbols are deliberately not re-exported
    at the package top level.
    """
    found: set[tuple[str, str]] = set()
    for path in (CLI_ROOT / "src").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("aevrin_scanner_core"):
                found.update((node.module, alias.name) for alias in node.names)
    return found


def test_declared_floor_is_not_behind_the_workspace_version():
    """The floor must cover the workspace copy the CLI is actually developed
    against. If scanner-core gains public API, both versions move together."""
    assert _declared_floor() >= _scanner_core_version(), (
        f"CLI declares aevrin-scanner-core>={'.'.join(map(str, _declared_floor()))} but the workspace "
        f"copy is {'.'.join(map(str, _scanner_core_version()))}. Bump the floor, or a PyPI install can "
        "resolve an older scanner-core that lacks symbols the CLI imports."
    )


def test_every_imported_symbol_exists_in_scanner_core():
    """Catches importing a symbol that simply doesn't exist, a typo, or a
    rename that only got applied on one side."""
    import importlib

    missing: list[str] = []
    for module_name, symbol in sorted(_symbols_imported_from_scanner_core()):
        module = importlib.import_module(module_name)
        if not hasattr(module, symbol):
            missing.append(f"{module_name}.{symbol}")

    assert not missing, f"CLI imports names that don't exist in scanner-core: {missing}"


def test_scanner_core_exports_the_autofix_eligibility_api():
    """The specific symbols whose absence caused the shipped ImportError."""
    import aevrin_scanner_core

    for name in ("is_autofix_eligible", "FIXABLE_TOOLS"):
        assert hasattr(aevrin_scanner_core, name), f"aevrin_scanner_core must export {name}"
