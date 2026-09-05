"""Supply-chain rules that read a repository's own manifests: AS-008,
AS-015 and AS-016.

This is the narrow, MCP-relevant slice of supply chain, not a general
dependency audit. The question is "would installing this MCP server run
something hostile, or pull in a package already known to be compromised" -
answerable from files in the clone, with no network call and no execution.
AS-004 (published CVEs in the dependency tree) is a separate, heavier check
and stays with the OSV-Scanner adapter.

The scope limit is real and is reported rather than hidden. A transitive
dependency's own install script lives in that package's registry metadata,
not in this repository, so it is out of reach here; AS-014 is what says so
when the inventory could not be read at all.

Data files under `data/` are vendored from the ToolTrust Scanner
(https://github.com/AgentSafe-AI/tooltrust-scanner, MIT, Copyright (c) 2026
AgentSafe-AI - full licence text in `data/TOOLTRUST-LICENSE.txt`). They are
threat intelligence, not code: the format is theirs, the matching below is
Aevrin's.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from uuid import UUID

from ..models import Finding, Location, Severity, ToolName
from .catalog import RULE_CATALOG

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# Bounds on how much of a repository this will read. A monorepo can contain
# thousands of manifests, and this runs inside a scan with a time budget.
_MAX_MANIFESTS = 60
_MAX_DEPTH = 4
_DIR_EXCLUDES = frozenset({
    ".git", "__pycache__", ".venv", "venv", "dist", "build", ".next", ".tox",
    "target", ".mypy_cache", ".pytest_cache",
})


@dataclass(frozen=True)
class Dependency:
    ecosystem: str
    name: str
    version: str
    manifest_path: str
    # Per the owning manifest's own dependency/devDependency split. AS-004
    # drops anything that is not "production": a CVE in a test-only package
    # is not part of what an agent runs.
    scope: str = "production"


def _finding(
    scan_id: UUID,
    rule_id: str,
    severity: Severity,
    description: str,
    *,
    evidence: list[str],
    manifest_path: str | None = None,
    title: str | None = None,
    remediation: str | None = None,
) -> Finding:
    rule = RULE_CATALOG[rule_id]
    return Finding(
        scan_id=scan_id,
        tool=ToolName.AEVRIN_MCP_RULES,
        rule_id=rule_id,
        owasp_category=rule.owasp,
        severity=severity,
        title=title or rule.title,
        description=description,
        remediation=remediation or rule.fix,
        evidence=evidence,
        location=Location(file_path=manifest_path),
    )


# --------------------------------------------------------------------------
# Manifest reading


def read_dependencies(repo_dir: str) -> list[Dependency]:
    """Declared direct dependencies, from the manifests a repository commits.

    Lockfiles are deliberately not parsed here: OSV-Scanner already reads
    them for AS-004 and does it better, and a second parser for the same
    files would be one more thing to keep correct.
    """
    dependencies: list[Dependency] = []
    for manifest_path, content in _walk_manifests(repo_dir):
        if manifest_path.endswith("package.json"):
            dependencies.extend(_parse_package_json(manifest_path, content))
        elif manifest_path.endswith(("requirements.txt", "requirements-dev.txt")):
            dependencies.extend(_parse_requirements(manifest_path, content))
        elif manifest_path.endswith("go.mod"):
            dependencies.extend(_parse_go_mod(manifest_path, content))
    return dependencies


def _walk_manifests(repo_dir: str) -> list[tuple[str, str]]:
    """Manifests this could actually read.

    A manifest that could not be opened is recorded in `unreadable_manifests`
    rather than skipped in silence. That is not a theoretical case: on a
    machine with endpoint protection, reading a `package.json` whose install
    script contains `curl … | bash` can fail with a hard OSError - the exact
    file the supply-chain rules most need to see. Losing it quietly would
    turn the most dangerous manifest in the tree into a clean result.
    """
    names = ("package.json", "requirements.txt", "requirements-dev.txt", "go.mod")
    found: list[tuple[str, str]] = []
    unreadable_manifests: list[tuple[str, str]] = []
    for root, dirs, files in os.walk(repo_dir):
        relative_root = os.path.relpath(root, repo_dir)
        depth = 0 if relative_root == "." else relative_root.count(os.sep) + 1
        if depth >= _MAX_DEPTH:
            dirs[:] = []
        # node_modules is walked one level deep only: a vendored dependency's
        # own package.json is exactly where an install-time script hides, and
        # the whole tree would be tens of thousands of files.
        dirs[:] = [
            d for d in dirs
            if d not in _DIR_EXCLUDES and (d != "node_modules" or depth == 0)
        ]
        for name in files:
            if name not in names:
                continue
            path = os.path.join(root, name)
            relative = os.path.relpath(path, repo_dir).replace(os.sep, "/")
            try:
                with open(path, encoding="utf-8", errors="ignore") as handle:
                    content = handle.read(512_000)
            except OSError as exc:
                unreadable_manifests.append((relative, f"{type(exc).__name__}: {exc.strerror}"))
                continue
            found.append((relative, content))
            if len(found) >= _MAX_MANIFESTS:
                _LAST_UNREADABLE.clear()
                _LAST_UNREADABLE.extend(unreadable_manifests)
                return found
    _LAST_UNREADABLE.clear()
    _LAST_UNREADABLE.extend(unreadable_manifests)
    return found


# Manifests the most recent `_walk_manifests` could not open. Module state
# rather than a second return value because three callers want the manifests
# and only `run_supply_chain_rules` wants this; threading an ignored tuple
# through the other two would be noise at every call site.
_LAST_UNREADABLE: list[tuple[str, str]] = []


def _parse_package_json(path: str, content: str) -> list[Dependency]:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    out: list[Dependency] = []
    for key, scope in (("dependencies", "production"), ("devDependencies", "development")):
        section = data.get(key)
        if not isinstance(section, dict):
            continue
        for name, version in section.items():
            if isinstance(name, str) and isinstance(version, str):
                out.append(Dependency("npm", name, version.lstrip("^~>=< "), path, scope))
    return out


_REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9._\-\[\]]+)\s*==\s*([A-Za-z0-9._\-+]+)")


def _parse_requirements(path: str, content: str) -> list[Dependency]:
    scope = "development" if "dev" in os.path.basename(path) else "production"
    out: list[Dependency] = []
    for line in content.splitlines():
        match = _REQUIREMENT.match(line)
        if match:
            out.append(Dependency("PyPI", match.group(1), match.group(2), path, scope))
    return out


_GO_REQUIRE = re.compile(r"^\s*([\w./\-]+)\s+(v[\w.\-+]+)")


def _parse_go_mod(path: str, content: str) -> list[Dependency]:
    out: list[Dependency] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(("module ", "go ", "require (", ")", "//")):
            continue
        match = _GO_REQUIRE.match(stripped.removeprefix("require "))
        if match:
            out.append(Dependency("Go", match.group(1), match.group(2), path))
    return out


# --------------------------------------------------------------------------
# AS-008  Known compromised package versions


@lru_cache(maxsize=1)
def _compromised_index() -> dict[str, list[dict[str, Any]]]:
    try:
        with open(os.path.join(_DATA_DIR, "compromised_packages.json"), encoding="utf-8") as handle:
            entries = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    index: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = f"{str(entry.get('ecosystem', '')).lower()}:{str(entry.get('component', '')).lower()}"
        index.setdefault(key, []).append(entry)
    return index


_SEVERITY_BY_NAME = {
    "CRITICAL": Severity.CRITICAL,
    "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
}


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", version.lstrip("v"))
    return tuple(int(p) for p in parts[:4]) or (0,)


def _version_matches(version: str, constraint: str) -> bool:
    constraint = constraint.strip()
    if constraint == "*":
        return True
    if constraint.startswith("<="):
        return _version_tuple(version) <= _version_tuple(constraint[2:])
    if constraint.startswith("<"):
        return _version_tuple(version) < _version_tuple(constraint[1:])
    return version.lstrip("v").lower() == constraint.lstrip("v").lower()


def check_compromised_packages(scan_id: UUID, dependencies: list[Dependency]) -> list[Finding]:
    index = _compromised_index()
    findings: list[Finding] = []
    seen: set[str] = set()
    for dependency in dependencies:
        for key in (
            f"{dependency.ecosystem.lower()}:{dependency.name.lower()}",
            # The catalogue also tracks compromised binaries and GitHub
            # Actions by bare name, with no ecosystem an npm/PyPI manifest
            # would ever match on.
            f"binary:{dependency.name.lower()}",
        ):
            for entry in index.get(key, []):
                versions = entry.get("affected_versions")
                if not isinstance(versions, list):
                    continue
                if not any(_version_matches(dependency.version, str(v)) for v in versions):
                    continue
                marker = f"{dependency.name}@{dependency.version}:{entry.get('id')}"
                if marker in seen:
                    continue
                seen.add(marker)
                findings.append(
                    _finding(
                        scan_id,
                        "AS-008",
                        _SEVERITY_BY_NAME.get(str(entry.get("severity", "")).upper(), Severity.CRITICAL),
                        (
                            f"{dependency.name}@{dependency.version} is a known-compromised "
                            f"release. {entry.get('reason', '')}".strip()
                        ),
                        evidence=[
                            f"package: {dependency.name}@{dependency.version}",
                            f"advisory: {entry.get('id', 'unknown')}",
                            f"manifest: {dependency.manifest_path}",
                        ],
                        manifest_path=dependency.manifest_path,
                    )
                )
    return findings


# --------------------------------------------------------------------------
# AS-015 / AS-016  Install-time scripts and malicious indicators

_LIFECYCLE_KEYS = ("preinstall", "install", "postinstall", "prepare")
_HIGH_RISK_SCRIPT_PATTERNS = (
    "curl ", "wget ", "powershell", "invoke-webrequest", "bash -c", "sh -c",
    "node -e", "python -c", "certutil",
)


@lru_cache(maxsize=1)
def _npm_iocs() -> tuple[dict[str, Any], ...]:
    try:
        with open(os.path.join(_DATA_DIR, "npm_iocs.json"), encoding="utf-8") as handle:
            entries = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return ()
    return tuple(e for e in entries if isinstance(e, dict))


def check_install_scripts(scan_id: UUID, repo_dir: str) -> list[Finding]:
    """Lifecycle scripts declared by this repository and by any package it
    vendors one level into `node_modules`."""
    findings: list[Finding] = []
    for manifest_path, content in _walk_manifests(repo_dir):
        if not manifest_path.endswith("package.json"):
            continue
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            continue
        scripts = data.get("scripts") if isinstance(data, dict) else None
        if not isinstance(scripts, dict):
            continue
        for key in _LIFECYCLE_KEYS:
            body = scripts.get(key)
            if not isinstance(body, str) or not body.strip():
                continue
            lowered = body.lower()
            risky = [p.strip() for p in _HIGH_RISK_SCRIPT_PATTERNS if p in lowered]
            findings.append(
                _finding(
                    scan_id,
                    "AS-015",
                    Severity.HIGH if risky else Severity.MEDIUM,
                    (
                        f"{manifest_path} runs a `{key}` script at install time"
                        + (f", using {', '.join(risky)}." if risky else ".")
                    ),
                    evidence=[f"{key}: {body[:200]}", f"manifest: {manifest_path}"],
                    manifest_path=manifest_path,
                )
            )
            findings.extend(_ioc_findings(scan_id, body, manifest_path, f"{key} script"))
    return findings


def check_dependency_iocs(scan_id: UUID, dependencies: list[Dependency]) -> list[Finding]:
    findings: list[Finding] = []
    for dependency in dependencies:
        if dependency.ecosystem.lower() != "npm":
            continue
        for entry in _npm_iocs():
            if entry.get("ioc_type") != "package_name":
                continue
            if str(entry.get("name", "")).lower() != dependency.name.lower():
                continue
            findings.append(
                _finding(
                    scan_id,
                    "AS-016",
                    Severity.CRITICAL,
                    (
                        f"{dependency.name} is a known malicious-campaign indicator. "
                        f"{entry.get('reason', '')}".strip()
                    ),
                    evidence=[
                        f"package: {dependency.name}",
                        f"confidence: {entry.get('confidence', 'unknown')}",
                        f"source: {entry.get('source', 'unknown')}",
                    ],
                    manifest_path=dependency.manifest_path,
                )
            )
    return findings


def _ioc_findings(scan_id: UUID, text: str, manifest_path: str, where: str) -> list[Finding]:
    lowered = text.lower()
    findings: list[Finding] = []
    for entry in _npm_iocs():
        ioc_type = entry.get("ioc_type")
        if ioc_type not in ("domain", "url", "script_pattern"):
            continue
        value = str(entry.get("value", "")).lower()
        if not value:
            continue
        matched = value == lowered if entry.get("match") == "exact" else value in lowered
        if not matched:
            continue
        findings.append(
            _finding(
                scan_id,
                "AS-016",
                Severity.CRITICAL,
                (
                    f"The {where} in {manifest_path} references a known malicious "
                    f"{ioc_type.replace('_', ' ')}. {entry.get('reason', '')}".strip()
                ),
                evidence=[
                    f"{ioc_type}: {entry.get('value')}",
                    f"confidence: {entry.get('confidence', 'unknown')}",
                    f"source: {entry.get('source', 'unknown')}",
                ],
                manifest_path=manifest_path,
            )
        )
    return findings


def run_supply_chain_rules(scan_id: UUID, repo_dir: str) -> tuple[list[Finding], list[Dependency]]:
    """Every manifest-driven supply-chain rule, plus the dependency list the
    caller needs to scope AS-004's CVE findings to production packages."""
    dependencies = read_dependencies(repo_dir)
    findings = [
        *check_compromised_packages(scan_id, dependencies),
        *check_dependency_iocs(scan_id, dependencies),
        *check_install_scripts(scan_id, repo_dir),
    ]
    unreadable = list(_LAST_UNREADABLE)
    if unreadable:
        findings.append(
            _finding(
                scan_id,
                "AS-014",
                Severity.INFO,
                (
                    f"{len(unreadable)} manifest file(s) could not be read, so the packages they "
                    "declare were not checked against the compromised-package and indicator "
                    "lists. This is missing coverage, not a clean result."
                ),
                evidence=[f"{path}: {reason}" for path, reason in unreadable[:10]],
                title="Manifest Unreadable",
            )
        )
    return findings, dependencies
