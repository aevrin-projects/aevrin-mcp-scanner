"""The MCP security engine: invoke the scanner, normalise what it returns.

This module is deliberately thin. Aevrin does not decide what is a
vulnerability, how severe it is, or what grade a tool earns - the scanner
does, and this file's only job is to turn its JSON into Aevrin `Finding`
objects without changing a single one of those judgements.

What the scanner gives us, verified by running it rather than read off a
README:

    {"schema_version": "1.0",
     "policies": [{"tool_name", "action", "reason", "behavior",
                   "dependency_visibility", "dependency_note",
                   "score": {"risk_score", "grade", "findings": [...]}}],
     "summary": {"total", "allowed", "require_approval", "blocked",
                 "avg_score", "avg_grade", "scanned_at"}}

Two consequences drive everything below.

**Grades are per tool, and the only roll-up offered is an average.** That
average cannot be shown to a user. On a real run, a five-tool server whose
`run_shell` tool carried a Critical tool-poisoning finding summarised as
`avg_grade: A`, because four boring tools outvoted it. A server is not safe
because most of its tools are; you install the whole server, and the worst
tool is the one that gets you. So the server-level grade is the worst tool's
grade, taken from the scanner unchanged - a selection over its output, never
a second scoring algorithm. See DECISIONS.md ADR-033.

**Findings carry no prose.** Each one has `rule_id`, `severity`, `code`,
`description`, `location` and `evidence`, and nothing that answers "why does
this matter" or "what do I change". That prose lives in `catalog.py`, keyed
by the same rule ids, and is joined on here. A rule id the catalogue does not
know still produces a finding - using the scanner's own `description` - because
dropping a real security finding for want of a title would be the worse bug.
"""

from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from ..classification.owasp import OwaspMcpCategory

# `_ANSI_RE` is shared rather than re-declared: two copies of a stripping
# regex drift, and the one that drifts is the one nobody is looking at.
from ..execution.runner import (
    _ANSI_RE,
    DockerRunSpec,
    ToolExecutionError,
    run_container,
)
from ..models import Finding, Location, Severity, ToolName
from .catalog import rule_for
from .risk import Grade, Policy

# The image carrying the pinned engine plus the runtimes an MCP server needs
# to start (node/npx, python/uvx). Overridable so a deployment can pin a
# digest; see backend/scanner-image/Dockerfile and docs/architecture/DEPLOYMENT.md.
SCANNER_IMAGE = os.environ.get("AEVRIN_SCANNER_IMAGE", "aevrin/mcp-scanner:0.3.19")

# Engine identity recorded per scan (§20). Not shown to users.
SCANNER_NAME = "tooltrust-scanner"
SCANNER_VERSION = "0.3.19"

# Launching a stranger's server is not a fast operation: npx has to resolve
# and install the package before the handshake can even be attempted. This is
# a ceiling on the whole thing, enforced by Docker rather than by asking the
# process nicely.
LAUNCH_TIMEOUT_S = 300

# Upstream severity strings to Aevrin's enum. Upstream is the authority on
# which one a finding gets; this only translates the spelling, and an
# unrecognised value becomes INFO rather than being guessed upward - inflating
# a severity we did not understand would be inventing a security claim.
_SEVERITY: dict[str, Severity] = {
    "CRITICAL": Severity.CRITICAL,
    "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
    "INFO": Severity.INFO,
}

_ACTIONS: dict[str, Policy] = {
    "ALLOW": Policy.ALLOW,
    "REQUIRE_APPROVAL": Policy.REQUIRE_APPROVAL,
    "BLOCK": Policy.BLOCK,
}

_GRADES: dict[str, Grade] = {g.value: g for g in Grade}

# Worst first. Used to pick the server-level grade; ordering the enum itself
# would give `Grade` a meaning it does not have anywhere else.
_GRADE_ORDER: list[Grade] = [Grade.F, Grade.D, Grade.C, Grade.B, Grade.A]

# Where a finding with no catalogue entry lands. MCP09 (excessive agency) is
# the honest default for "the scanner found something about this tool's
# behaviour that we have no prose for yet".
_FALLBACK_CATEGORY = OwaspMcpCategory.EXCESSIVE_AGENCY


class ScannerOutputError(ValueError):
    """The scanner produced something this cannot read.

    Raised rather than absorbed: a scan whose output could not be parsed is
    an incomplete scan, and the pipeline has to be able to tell that apart
    from a scan that genuinely found nothing.
    """


@dataclass(frozen=True)
class ToolPolicy:
    """One tool's verdict, exactly as the scanner issued it."""

    tool_name: str
    action: Policy
    grade: Grade
    risk_score: int
    reason: str = ""
    behavior: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScanReport:
    """The normalised result of one scanner run."""

    tools: tuple[str, ...]
    policies: tuple[ToolPolicy, ...]
    findings: list[Finding]
    # None when the scanner returned no tools at all: there is nothing to
    # grade, and a letter would be a claim about evidence nobody has.
    risk_score: int | None
    grade: Grade | None
    policy: Policy
    dependency_visibility: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def _evidence_lines(finding: dict[str, Any]) -> list[str]:
    """The specific facts that made this rule fire.

    The scanner's `description` is included as the first line because it is
    the only place that says *what* matched for this particular tool; the
    catalogue's prose is about the rule in general, not this instance.
    """
    lines: list[str] = []
    description = str(finding.get("description") or "").strip()
    if description:
        lines.append(description)
    for item in finding.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        value = str(item.get("value") or "").strip()
        if kind and value:
            lines.append(f"{kind}: {value}")
        elif value:
            lines.append(value)
    location = str(finding.get("location") or "").strip()
    if location:
        lines.append(f"location: {location}")
    return lines


def _finding_from(raw: dict[str, Any], *, scan_id: UUID, tool_name: str) -> Finding:
    rule_id = str(raw.get("rule_id") or "").strip() or None
    rule = rule_for(rule_id)
    severity = _SEVERITY.get(str(raw.get("severity") or "").upper(), Severity.INFO)

    # `code` is the scanner's machine-readable label (ARBITRARY_CODE_EXECUTION).
    # It is a usable title when the catalogue has no entry, but it is shouty,
    # so it is only a fallback and is de-screamed on the way through.
    code = str(raw.get("code") or "").strip()
    fallback_title = code.replace("_", " ").title() if code else "Security finding"

    return Finding(
        scan_id=scan_id,
        tool=ToolName.MCP_SCANNER,
        rule_id=rule_id,
        owasp_category=rule.owasp if rule else _FALLBACK_CATEGORY,
        severity=severity,
        title=rule.title if rule else fallback_title,
        description=str(raw.get("description") or "").strip(),
        remediation=rule.fix if rule else "",
        location=Location(tool_name_in_manifest=tool_name or None),
        evidence=_evidence_lines(raw),
        affected_tools=[tool_name] if tool_name else [],
        raw=raw,
    )


def _worst(policies: list[ToolPolicy]) -> ToolPolicy | None:
    """The tool that decides the server's grade.

    Ordered by the scanner's grade first and its risk score second, so two
    tools sharing a letter are separated by the number the scanner already
    computed rather than by anything invented here.
    """
    if not policies:
        return None
    return max(
        policies,
        key=lambda p: (-_GRADE_ORDER.index(p.grade), p.risk_score),
    )


class ServerLaunchError(Exception):
    """The server could not be started, or did not complete a handshake.

    Distinct from `ScannerOutputError`: this one means there was nothing to
    analyse, which is the common and legitimate outcome for a server needing
    credentials, a browser, or a package that was never published.
    """


# Where the engine stops reporting an error and starts printing its manual.
# A usage block is the tail of stderr on a usage error, which is exactly what
# a tail-truncated excerpt keeps and precisely what a user cannot act on.
# Everything from the first of these onward is dropped.
_USAGE_BLOCK_RE = re.compile(
    r"^\s*(Usage|Flags|Examples|Global Flags|Available Commands)\s*:"
    r"|^\s*(-\w,\s*)?--\w[\w-]*\b",
    re.IGNORECASE,
)
# §21: a user is never told which engine produced their scan, so its binary
# name must not travel out on an error path either.
_ENGINE_NAMES_RE = re.compile(r"(?i)\b(mcp-scanner|tooltrust[\w-]*|agentsafe[\w-]*)\b")


def _launch_reason(stderr: str, fallback: str) -> str:
    """The part of a launch failure a user can actually act on.

    `npx` reports the real cause on its first lines ("404 Not Found",
    "command not found", a stack trace's first frame); an engine usage error
    puts a flag list after it. `ToolExecutionError` keeps the *last* 600
    characters, so the useful sentence is the part that gets dropped - this
    reads from the front instead, and drops the usage block entirely.
    """
    kept: list[str] = []
    for line in _ANSI_RE.sub("", stderr).splitlines():
        if _USAGE_BLOCK_RE.match(line):
            break  # the manual starts here; nothing after it is diagnostic
        if line.strip():
            kept.append(line.strip())
    reason = " ".join(kept[:3])[:300].strip() or fallback
    return _ENGINE_NAMES_RE.sub("the scan engine", reason).strip()


def scan_live_server(command: str, *, scan_id: UUID) -> ScanReport:
    """Launch an MCP server, enumerate its tools, and analyse them.

    Everything here happens inside a one-shot container, and the reason is
    worth being explicit about: `command` is typically `npx -y <package>`,
    which downloads and executes code chosen by whoever published that
    package. npm runs `preinstall`/`postinstall` scripts during installation,
    so arbitrary code executes *before* any scanning begins.

    Running that in the API process would give a hostile package the
    Supabase service-role key, which bypasses RLS and is therefore the whole
    tenancy boundary. So the container gets:

    * no environment from the host - `env` is an explicit allow-list and is
      empty apart from the paths npx needs
    * a read-only root filesystem with writable tmpfs only
    * a non-root uid, every capability dropped, no-new-privileges
    * memory, CPU and pid ceilings, and a hard wall-clock timeout
    * `--rm`, so the filesystem does not outlive the scan

    Network access is required (the package has to be downloaded) and is
    therefore the residual exposure. On the deployed host, EC2 IMDSv2 with a
    hop limit of 1 already refuses a request from behind Docker's NAT, which
    is what stops this container reaching instance credentials; that setting
    is a deployment precondition rather than something this code can enforce.
    """
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise ServerLaunchError(f"server command could not be parsed: {exc}") from exc
    if not argv:
        raise ServerLaunchError("server command was empty")

    spec = DockerRunSpec(
        image=SCANNER_IMAGE,
        args=["scan", "--server", command, "--output", "json"],
        # Required: the package must be fetched before it can be launched.
        network_enabled=True,
        timeout_s=LAUNCH_TIMEOUT_S,
        mem_limit="2g",
        cpus="2.0",
        read_only_rootfs=True,
        # `exec` is present deliberately: npx installs shim scripts here and
        # execs them, so a noexec install prefix would prevent the scan
        # rather than harden it. Isolation comes from the container being
        # credential-free and disposable, not from this mount option.
        tmpfs={
            "/tmp": "rw,nosuid,exec,size=1g",
            "/home/scanner": "rw,nosuid,exec,size=1g",
        },
        user="10002:10002",
        env={"HOME": "/home/scanner", "NPM_CONFIG_CACHE": "/tmp/.npm", "NO_COLOR": "1"},
        workdir="/tmp",
    )

    try:
        stdout, stderr, _ = run_container("mcp-scanner", spec)
    except ToolExecutionError as exc:
        # The upstream message names the binary and its flags, and the caller
        # interpolates this straight into a stage error a user reads. Sanitise
        # here rather than trusting every call site to remember: the full
        # detail stays reachable through `__cause__` for logs.
        raise ServerLaunchError(
            _launch_reason(exc.stderr, "the server exited before completing a handshake")
        ) from exc

    if not stdout.strip():
        raise ServerLaunchError(
            _launch_reason(stderr, "the server produced no scan output")
        )
    return parse_report(stdout, scan_id=scan_id)


def parse_report(payload: dict[str, Any] | str, *, scan_id: UUID) -> ScanReport:
    """Turn one scanner JSON document into Aevrin's model.

    Raises `ScannerOutputError` for anything it cannot read, rather than
    returning an empty-looking result that would render as a clean scan.
    """
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ScannerOutputError(f"scanner output was not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ScannerOutputError("scanner output was not a JSON object")

    raw_policies = payload.get("policies")
    if raw_policies is None:
        raise ScannerOutputError("scanner output carried no 'policies' key")
    if not isinstance(raw_policies, list):
        raise ScannerOutputError("scanner 'policies' was not a list")

    policies: list[ToolPolicy] = []
    findings: list[Finding] = []
    tools: list[str] = []
    dependency_visibility: str | None = None

    for entry in raw_policies:
        if not isinstance(entry, dict):
            continue
        tool_name = str(entry.get("tool_name") or "").strip()
        if tool_name:
            tools.append(tool_name)
        if dependency_visibility is None:
            visibility = entry.get("dependency_visibility")
            if visibility:
                dependency_visibility = str(visibility)

        score = entry.get("score")
        score = score if isinstance(score, dict) else {}
        grade = _GRADES.get(str(score.get("grade") or "").upper())
        action = _ACTIONS.get(str(entry.get("action") or "").upper())
        if grade is not None and action is not None:
            behavior = entry.get("behavior")
            policies.append(
                ToolPolicy(
                    tool_name=tool_name,
                    action=action,
                    grade=grade,
                    risk_score=int(score.get("risk_score") or 0),
                    reason=str(entry.get("reason") or ""),
                    behavior=tuple(str(b) for b in behavior) if isinstance(behavior, list) else (),
                )
            )

        for raw_finding in score.get("findings") or []:
            if isinstance(raw_finding, dict):
                findings.append(
                    _finding_from(raw_finding, scan_id=scan_id, tool_name=tool_name)
                )

    worst = _worst(policies)
    return ScanReport(
        tools=tuple(tools),
        policies=tuple(policies),
        findings=findings,
        risk_score=worst.risk_score if worst else None,
        grade=worst.grade if worst else None,
        # No tools enumerated is not "allow". Nothing was established, so the
        # only honest recommendation is that a human look.
        policy=worst.action if worst else Policy.REQUIRE_APPROVAL,
        dependency_visibility=dependency_visibility,
        raw=payload,
    )
