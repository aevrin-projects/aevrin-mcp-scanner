"""Our own rule-lookup heuristics for the three OWASP MCP categories the
master spec explicitly says are "not a model" — plain presence/schema checks,
per Section 4 rows 6, 9, and 10. These run in-process (no container), inside
the `tool_description_check` stage alongside MCP-Shield and SDK inspection.
"""

from __future__ import annotations

import os
import re
from uuid import UUID

from .models import Finding, Location, Severity, ToolName
from .owasp import OwaspMcpCategory

# Row 9 — tool names/descriptions implying broad, dangerous capability with no
# apparent scoping. Presence of these terms doesn't prove overreach, but their
# presence with no counterbalancing scope declaration is the signal we can
# check statically without a model.
_HIGH_PRIVILEGE_TERMS = re.compile(
    r"\b(?:exec(?:ute)?|shell|sudo|admin|delete|drop\s+table|rm\s+-rf|chmod|"
    r"write[_\s]?file|read[_\s]?any|full[_\s]?access|unrestricted)\b",
    re.IGNORECASE,
)

_LOGGING_IMPORT_PATTERNS = [
    re.compile(r"^\s*import\s+logging\b", re.MULTILINE),
    re.compile(r"^\s*from\s+logging\b", re.MULTILINE),
    re.compile(r"\brequire\(['\"]winston['\"]\)"),
    re.compile(r"\brequire\(['\"]pino['\"]\)"),
    re.compile(r"\bimport\s+.*from\s+['\"]winston['\"]"),
    re.compile(r"\baudit[_-]?log\b", re.IGNORECASE),
]

_SOURCE_EXTENSIONS = (".py", ".js", ".ts", ".mjs", ".cjs", ".go", ".rb")


class ToolDescriptor:
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description


class TransportInfo:
    def __init__(self, url: str | None, has_auth_header: bool, has_api_key_env: bool):
        self.url = url
        self.has_auth_header = has_auth_header
        self.has_api_key_env = has_api_key_env


def check_excessive_agency(scan_id: UUID, tools: list[ToolDescriptor]) -> list[Finding]:
    findings: list[Finding] = []
    for t in tools:
        matches = sorted({m.lower() for m in _HIGH_PRIVILEGE_TERMS.findall(t.description + " " + t.name)})
        if not matches:
            continue
        findings.append(
            Finding(
                scan_id=scan_id,
                tool=ToolName.AEVRIN_MANIFEST_RULES,
                owasp_category=OwaspMcpCategory.EXCESSIVE_AGENCY,
                severity=Severity.MEDIUM,
                title=f"Broad-capability tool declared: {t.name}",
                description=(
                    f"Tool '{t.name}' description implies high-privilege capability "
                    f"({', '.join(matches)}) with no scoping declared. Declared-scope check "
                    "only — this does not confirm actual overreach, only that the manifest "
                    "doesn't limit it."
                ),
                location=Location(manifest_field="tools[].description", tool_name_in_manifest=t.name),
                remediation=(
                    "Scope this tool to the minimum capability it needs, and document the "
                    "scope explicitly in its description."
                ),
                raw={"tool": t.name, "matched_terms": matches},
            )
        )
    return findings


def check_weak_auth(scan_id: UUID, transport: TransportInfo) -> list[Finding]:
    findings: list[Finding] = []
    if transport.url and transport.url.startswith("http://"):
        findings.append(
            Finding(
                scan_id=scan_id,
                tool=ToolName.AEVRIN_MANIFEST_RULES,
                owasp_category=OwaspMcpCategory.WEAK_AUTH,
                severity=Severity.HIGH,
                title="MCP server reachable over plaintext HTTP",
                description=f"{transport.url} is not served over TLS.",
                location=Location(manifest_field="url"),
                remediation="Serve this MCP endpoint over HTTPS.",
            )
        )
    if transport.url and not transport.has_auth_header and not transport.has_api_key_env:
        findings.append(
            Finding(
                scan_id=scan_id,
                tool=ToolName.AEVRIN_MANIFEST_RULES,
                owasp_category=OwaspMcpCategory.WEAK_AUTH,
                severity=Severity.MEDIUM,
                title="No authentication declared for this MCP server",
                description=(
                    "Presence-only check: no Authorization header or API-key environment "
                    "variable found in the server config. This does not confirm the server "
                    "is actually open — only that the config doesn't declare auth."
                ),
                location=Location(manifest_field="headers/env"),
                remediation="Require an API key, bearer token, or OAuth flow for this server.",
            )
        )
    return findings


# Row 1 — what a stdio MCP entry actually *executes* on your machine the
# moment you install it. This is the only signal available for a stdio
# server: there is no URL to probe and, for a pasted config, no source to
# scan. Every pattern here is a literal command shape, not a guess about
# intent.
_SHELL_INTERPRETERS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "cmd", "cmd.exe", "powershell", "pwsh"})

# Fetch piped straight into an interpreter — the classic remote-code-execution
# install shape.
_PIPE_TO_SHELL = re.compile(
    r"\b(?:curl|wget|iwr|invoke-webrequest)\b[^|;&]*[|]\s*(?:sudo\s+)?(?:sh|bash|zsh|python[23]?|node|perl|ruby)\b",
    re.IGNORECASE,
)
# Decode-then-execute, the usual way an obfuscated payload is smuggled.
_ENCODED_EXEC = re.compile(
    r"\b(?:base64\s+(?:-d|--decode)|atob|frombase64string)\b[^|;&]*[|]\s*(?:sh|bash|python[23]?|node)\b"
    r"|\b(?:eval|exec)\s*\(\s*(?:atob|base64)",
    re.IGNORECASE,
)


def check_dangerous_launch_command(
    scan_id: UUID, entries: dict[str, dict[str, object]]
) -> list[Finding]:
    """Inspects the command a stdio MCP entry runs on install.

    A pasted config previously produced no findings at all for stdio
    servers: clone/static/secrets/dependency stages are all skipped for that
    target type, and the remaining checks need either a URL or declared
    tools. A config whose server ran `sh -c "curl …|sh"` therefore scored a
    clean 100/100 — the exact install this product exists to warn about.
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
                Finding(
                    scan_id=scan_id,
                    tool=ToolName.AEVRIN_MANIFEST_RULES,
                    owasp_category=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
                    severity=Severity.CRITICAL,
                    title=f"Server '{name}' pipes downloaded content into a shell",
                    description=(
                        f"The launch command for '{name}' fetches remote content and executes it "
                        f"directly: {full[:300]}. Installing this server runs whatever that URL "
                        "serves, at the moment of install and on every subsequent start, with "
                        "your user's privileges."
                    ),
                    location=Location(manifest_field="command/args", tool_name_in_manifest=name),
                    remediation=(
                        "Do not install this server. If you control it, pin an installed package "
                        "or a checked-in script instead of executing fetched content."
                    ),
                    raw={"server": name, "command": command, "args": args},
                )
            )
            continue

        if basename in _SHELL_INTERPRETERS:
            findings.append(
                Finding(
                    scan_id=scan_id,
                    tool=ToolName.AEVRIN_MANIFEST_RULES,
                    owasp_category=OwaspMcpCategory.EXCESSIVE_AGENCY,
                    severity=Severity.HIGH,
                    title=f"Server '{name}' launches through a shell interpreter",
                    description=(
                        f"'{name}' starts via '{command}' rather than running a program directly, "
                        f"so its full command line is interpreted by a shell: {full[:300]}. That "
                        "allows shell metacharacters, chained commands, and redirection at "
                        "startup. This reports the launch shape only — it does not confirm the "
                        "command is malicious."
                    ),
                    location=Location(manifest_field="command/args", tool_name_in_manifest=name),
                    remediation=(
                        "Invoke the server binary or package entrypoint directly instead of "
                        "wrapping it in a shell."
                    ),
                    raw={"server": name, "command": command, "args": args},
                )
            )
    return findings


def check_audit_logging_presence(scan_id: UUID, repo_dir: str) -> list[Finding]:
    """Informational only, per Section 4 row 10 — presence of *any* logging
    import is a weak positive signal, absence is a weak negative signal.
    Walks up to 500 source files to stay fast on large repos."""
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
            path = os.path.join(root, name)
            try:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    content = f.read(20_000)
            except OSError:
                continue
            if any(p.search(content) for p in _LOGGING_IMPORT_PATTERNS):
                found_logging = True
                break
        if found_logging or scanned > 500:
            break

    if found_logging:
        return []  # clean — no finding, but the "informational only" caveat still applies at report level

    return [
        Finding(
            scan_id=scan_id,
            tool=ToolName.AEVRIN_MANIFEST_RULES,
            owasp_category=OwaspMcpCategory.WEAK_AUDIT_LOGGING,
            severity=Severity.INFO,
            title="No logging library usage detected",
            description=(
                "Source presence check only: no logging/audit-log imports found in the "
                "first 500 scanned source files. This is informational, not a confirmed gap "
                "— the project may log via a mechanism this heuristic doesn't recognize."
            ),
            location=Location(),
            remediation="Add structured audit logging for tool invocations, especially "
            "privileged ones.",
        )
    ]
