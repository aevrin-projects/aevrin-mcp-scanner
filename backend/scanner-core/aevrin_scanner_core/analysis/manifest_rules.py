"""Aevrin's own MCP rules, the ones with no ToolTrust equivalent: what a
server's launch command runs, whether its transport carries authentication,
and whether it logs anything at all.

Everything here reads a declaration - a config entry, a URL, an import line
- and runs in-process. Nothing is executed and nothing is connected to.

Two checks that used to live here are gone. `check_excessive_agency` scored
tool names against a keyword regex and `check_tool_name_shadowing` compared
them with `difflib`; both are now covered properly by `mcp/rules.py`
(AS-002/AS-003 read inferred permissions rather than keywords, AS-013
matches normalized names rather than a similarity ratio that fired on every
legitimate get/set pair). Keeping a weaker second implementation of a rule
the engine already runs is exactly the duplication this codebase forbids.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from uuid import UUID

from ..mcp.catalog import RULE_CATALOG
from ..models import Finding, Location, Severity, ToolName

_LOGGING_IMPORT_PATTERNS = [
    re.compile(r"^\s*import\s+logging\b", re.MULTILINE),
    re.compile(r"^\s*from\s+logging\b", re.MULTILINE),
    re.compile(r"\brequire\(['\"]winston['\"]\)"),
    re.compile(r"\brequire\(['\"]pino['\"]\)"),
    re.compile(r"\bimport\s+.*from\s+['\"]winston['\"]"),
    re.compile(r"\baudit[_-]?log\b", re.IGNORECASE),
]

_SOURCE_EXTENSIONS = (".py", ".js", ".ts", ".mjs", ".cjs", ".go", ".rb")


@dataclass(frozen=True)
class TransportInfo:
    url: str | None
    has_auth_header: bool
    has_api_key_env: bool


def _finding(
    scan_id: UUID,
    rule_id: str,
    severity: Severity,
    title: str,
    description: str,
    *,
    evidence: list[str],
    location: Location | None = None,
    remediation: str | None = None,
    affected_tools: list[str] | None = None,
    raw: dict[str, object] | None = None,
) -> Finding:
    rule = RULE_CATALOG[rule_id]
    return Finding(
        scan_id=scan_id,
        tool=ToolName.AEVRIN_MANIFEST_RULES,
        rule_id=rule_id,
        owasp_category=rule.owasp,
        severity=severity,
        title=title,
        description=description,
        remediation=remediation or rule.fix,
        evidence=evidence,
        affected_tools=affected_tools or [],
        location=location or Location(),
        raw=raw,
    )


# --------------------------------------------------------------------------
# AV-002  Transport authentication


def check_weak_auth(scan_id: UUID, transport: TransportInfo) -> list[Finding]:
    findings: list[Finding] = []
    if transport.url and transport.url.startswith("http://"):
        findings.append(
            _finding(
                scan_id,
                "AV-002",
                Severity.HIGH,
                "MCP server reachable over plaintext HTTP",
                f"{transport.url} is not served over TLS, so tool arguments and results, "
                "including any credential they carry, travel in the clear.",
                evidence=[f"url: {transport.url}"],
                location=Location(manifest_field="url"),
            )
        )
    if transport.url and not transport.has_auth_header and not transport.has_api_key_env:
        findings.append(
            _finding(
                scan_id,
                "AV-002",
                Severity.MEDIUM,
                "No authentication declared for this MCP server",
                (
                    "Presence check only: no Authorization header and no API-key environment "
                    "variable appear in this server's configuration. That does not confirm the "
                    "endpoint is open, only that nothing here declares a credential for it."
                ),
                evidence=["authorization header: absent", "api key environment variable: absent"],
                location=Location(manifest_field="headers/env"),
            )
        )
    return findings


# --------------------------------------------------------------------------
# AV-001  What a stdio entry actually executes on install
#
# The only signal available for a stdio server: there is no URL to probe
# and, for a pasted config, no source to read. Every pattern is a literal
# command shape, not a guess about intent.

_SHELL_INTERPRETERS = frozenset({
    "sh", "bash", "zsh", "dash", "ksh", "cmd", "cmd.exe", "powershell", "pwsh",
})

# Fetch piped straight into an interpreter: the classic remote-code-execution
# install shape.
_PIPE_TO_SHELL = re.compile(
    r"\b(?:curl|wget|iwr|invoke-webrequest)\b[^|;&]*[|]\s*(?:sudo\s+)?"
    r"(?:sh|bash|zsh|python[23]?|node|perl|ruby)\b",
    re.IGNORECASE,
)
# Decode-then-execute, the usual way an obfuscated payload is smuggled.
_ENCODED_EXEC = re.compile(
    r"\b(?:base64\s+(?:-d|--decode)|atob|frombase64string)\b[^|;&]*[|]\s*"
    r"(?:sh|bash|python[23]?|node)\b"
    r"|\b(?:eval|exec)\s*\(\s*(?:atob|base64)",
    re.IGNORECASE,
)


def check_dangerous_launch_command(
    scan_id: UUID, entries: dict[str, dict[str, object]]
) -> list[Finding]:
    """Inspects the command a stdio MCP entry runs on install.

    A pasted stdio config has no repository to read and no endpoint to
    probe, so without this it produced no findings at all - a server
    launching `sh -c "curl …|sh"` scored perfectly clean. This is the check
    that has to survive when every other one is inapplicable.
    """
    findings: list[Finding] = []
    for name, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        command = str(entry.get("command") or "")
        raw_args = entry.get("args") or []
        args = [str(a) for a in raw_args] if isinstance(raw_args, list) else []
        if not command:
            continue

        full = " ".join([command, *args])
        basename = os.path.basename(command).lower()

        if _PIPE_TO_SHELL.search(full) or _ENCODED_EXEC.search(full):
            findings.append(
                _finding(
                    scan_id,
                    "AV-001",
                    Severity.CRITICAL,
                    f"Server '{name}' pipes downloaded content into a shell",
                    (
                        f"The launch command for '{name}' fetches remote content and executes it "
                        "directly. Installing this server runs whatever that URL serves, at "
                        "install time and on every subsequent start, with your user's privileges."
                    ),
                    evidence=[f"launch command: {full[:300]}"],
                    location=Location(manifest_field="command/args", tool_name_in_manifest=name),
                    affected_tools=[name],
                    raw={"server": name, "command": command, "args": args},
                )
            )
            continue

        if basename in _SHELL_INTERPRETERS:
            findings.append(
                _finding(
                    scan_id,
                    "AV-001",
                    Severity.HIGH,
                    f"Server '{name}' launches through a shell interpreter",
                    (
                        f"'{name}' starts via '{command}' rather than running a program directly, "
                        "so its whole command line is interpreted by a shell: metacharacters, "
                        "chained commands and redirection all apply at startup. This reports the "
                        "launch shape; it does not claim the command is malicious."
                    ),
                    evidence=[f"interpreter: {basename}", f"launch command: {full[:300]}"],
                    location=Location(manifest_field="command/args", tool_name_in_manifest=name),
                    affected_tools=[name],
                    raw={"server": name, "command": command, "args": args},
                )
            )
    return findings


# --------------------------------------------------------------------------
# AV-003  Audit logging presence


def check_audit_logging_presence(scan_id: UUID, repo_dir: str) -> list[Finding]:
    """Presence of any logging import is a weak positive signal; absence is a
    weak negative one. Bounded to 500 source files to stay fast on a monorepo."""
    found_logging = False
    scanned = 0
    for root, _dirs, files in os.walk(repo_dir):
        if ".git" in root:
            continue
        for name in files:
            if not name.endswith(_SOURCE_EXTENSIONS):
                continue
            scanned += 1
            if scanned > 500:
                break
            try:
                with open(os.path.join(root, name), encoding="utf-8", errors="ignore") as handle:
                    content = handle.read(20_000)
            except OSError:
                continue
            if any(pattern.search(content) for pattern in _LOGGING_IMPORT_PATTERNS):
                found_logging = True
                break
        if found_logging or scanned > 500:
            break

    if found_logging:
        return []

    return [
        _finding(
            scan_id,
            "AV-003",
            Severity.INFO,
            "No logging library usage detected",
            (
                f"Source presence check only: no logging or audit-log import was found in the "
                f"{min(scanned, 500)} source files read. This is informational, not a confirmed "
                "gap - the project may log through a mechanism this does not recognise."
            ),
            evidence=[f"source files read: {min(scanned, 500)}", "logging import: none found"],
        )
    ]
