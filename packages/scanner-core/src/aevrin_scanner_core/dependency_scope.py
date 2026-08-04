"""Dev-vs-prod awareness for dependency findings (accuracy fix #6).

Checked both tools' actual JSON output before writing any of this, per the
brief: neither OSV-Scanner's nor Trivy's JSON exposes a per-finding dev/prod
flag for the `scan source` / `fs` invocations these adapters use.
OSV-Scanner's own `--ignore-dev` flag proves it *knows* the distinction
internally, but that knowledge isn't surfaced in JSON output — only used to
filter before the report is written, and we don't pass that flag (we want to
see dev-only findings, just weighted down, not silently dropped). Trivy's
`fs` scanner already excludes npm devDependencies by default (confirmed:
`--include-dev-deps` is required to include them, and this adapter's
invocation doesn't pass it) — so Trivy's npm findings are implicitly
production-only already; this module's manifest parsing is what actually
adds the missing signal for pip and for anything else Trivy still reports.

Scope is resolved repo-wide, not per-subpackage: in a monorepo where the
same package name is a dev dependency in one sub-package and a production
dependency in another, this treats it as PRODUCTION everywhere. That can
only under-count dev-only findings, never mask a real production risk.

Reachability (whether a vulnerable *transitive* dependency is actually
imported/executed at runtime) is intentionally NOT attempted here — neither
tool's JSON exposes a direct/transitive marker or a call graph for this
invocation, and building one from scratch is real static-analysis work well
beyond a manifest-parsing pass. This module only ever answers dev-vs-prod.
"""

from __future__ import annotations

import json
import os
import re

from .models import DependencyScope, Finding, ToolName
from .severity_utils import downweight_one_tier

_SCAN_DIR_EXCLUDES = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"})
_MAX_DEPTH = 4

_TITLE_PKG_RE = re.compile(r"^\S+ in (?P<pkg>.+)$")
_REQ_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)")

_DEPENDENCY_TOOLS = frozenset({ToolName.OSV_SCANNER, ToolName.TRIVY})


def _package_name(finding: Finding) -> str | None:
    match = _TITLE_PKG_RE.match(finding.title)
    if not match:
        return None
    return match.group("pkg").split("@")[0].strip().lower()


def _parse_package_json(path: str, dev: set[str], prod: set[str]) -> None:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    dev.update(k.lower() for k in (data.get("devDependencies") or {}))
    for key in ("dependencies", "peerDependencies", "optionalDependencies"):
        prod.update(k.lower() for k in (data.get(key) or {}))


def _parse_requirements_dev(path: str, dev: set[str]) -> None:
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return
    for raw_line in lines:
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = _REQ_LINE_RE.match(line)
        if match:
            dev.add(match.group(1).lower())


def _extract_section(text: str, header: str) -> str:
    """Best-effort TOML/INI section body, from `[header]` to the next
    top-level `[`. Not a real TOML parser — scanner-core targets Python
    3.10, where tomllib isn't in the stdlib yet, and dev-dependency sections
    are consistently a flat `name = ...` list, which a regex covers fine
    without adding a new dependency for one field."""
    match = re.search(rf"^\[{re.escape(header)}\]\s*$", text, re.MULTILINE)
    if not match:
        return ""
    rest = text[match.end() :]
    end = re.search(r"^\[", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


def _parse_pyproject_or_pipfile(path: str, dev: set[str]) -> None:
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return
    # Pipfile [dev-packages], Poetry's [tool.poetry.dev-dependencies] / the
    # newer per-group table — all flat `name = ...` sections.
    for header in (
        "dev-packages",
        "tool.poetry.dev-dependencies",
        "tool.poetry.group.dev.dependencies",
    ):
        for line in _extract_section(text, header).splitlines():
            match = _REQ_LINE_RE.match(line)
            if match:
                dev.add(match.group(1).lower())
    # PEP 735 [dependency-groups] dev = ["pytest>=8", ...]
    dev_array = re.search(r"dev\s*=\s*\[(.*?)]", _extract_section(text, "dependency-groups"), re.DOTALL)
    if dev_array:
        for name in re.findall(r"[\"']([A-Za-z0-9_.\-]+)", dev_array.group(1)):
            dev.add(name.lower())


def _collect_manifest_scopes(repo_dir: str) -> tuple[set[str], set[str]]:
    dev: set[str] = set()
    prod: set[str] = set()
    root_depth = repo_dir.rstrip("/").count("/")
    for dirpath, dirnames, filenames in os.walk(repo_dir):
        if dirpath.rstrip("/").count("/") - root_depth > _MAX_DEPTH:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in _SCAN_DIR_EXCLUDES]
        for filename in filenames:
            path = os.path.join(dirpath, filename)
            if filename == "package.json":
                _parse_package_json(path, dev, prod)
            elif filename in ("requirements-dev.txt", "dev-requirements.txt"):
                _parse_requirements_dev(path, dev)
            elif filename in ("Pipfile", "pyproject.toml"):
                _parse_pyproject_or_pipfile(path, dev)
    return dev, prod


def apply_dependency_scope(findings: list[Finding], repo_dir: str | None) -> None:
    """Mutates dependency findings in place: sets dependency_scope always
    when resolvable, and downweights severity one tier for packages
    resolved as dev-only — never deletes, matching the fixture-path
    exclusion precedent (downweighted/bucketed, still visible)."""
    if not repo_dir or not os.path.isdir(repo_dir):
        return
    dependency_findings = [f for f in findings if f.tool in _DEPENDENCY_TOOLS and f.raw]
    if not dependency_findings:
        return
    dev_packages, prod_packages = _collect_manifest_scopes(repo_dir)
    if not dev_packages and not prod_packages:
        return
    for finding in dependency_findings:
        pkg = _package_name(finding)
        if pkg is None:
            continue
        if pkg in prod_packages:
            finding.dependency_scope = DependencyScope.PRODUCTION
        elif pkg in dev_packages:
            finding.dependency_scope = DependencyScope.DEVELOPMENT
            if finding.original_severity is None:
                finding.original_severity = finding.severity
            finding.severity = downweight_one_tier(finding.severity)
        else:
            finding.dependency_scope = DependencyScope.UNKNOWN
