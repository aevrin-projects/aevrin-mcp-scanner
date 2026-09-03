"""Aevrin's own MCP-aware Semgrep taint rule pack.

`SemgrepAdapter` runs the public `p/security-audit`/`p/owasp-top-ten`/
`p/python` packs and hardcodes every finding it produces to one OWASP MCP
category (INJECTION_TRAVERSAL_SSRF), which is wrong for a hardcoded-secret
rule. This is a *separate* adapter, running only `rules/mcp/*.yaml`, because
the rules here declare their own category and capability in their own
`metadata` block (`aevrin-owasp`, `aevrin-capability`), read per-finding
rather than assumed once for the whole tool the way SemgrepAdapter's is.

The rule pack answers "does an MCP tool argument reach a dangerous sink" -
`subprocess.run`, a filesystem write, an outbound request, a credential
path - using Semgrep's own `mode: taint` with the tool's own decorated
handler parameters as the taint source. This is real dataflow evidence, not
a name/description guess, which is what `analysis.mcp_detection._classify`
alone can be defeated by (a poisoned description that omits dangerous
verbs).

**Every rule is intra-procedural.** Semgrep's open-source engine cannot
track taint across a function boundary - "sees the sink inside a helper the
tool handler calls" is a documented, deliberate gap here, not an oversight;
closing it needs either a paid Semgrep engine (rejected - see
`EXTERNAL_SCANNERS.md`) or a bounded reachability graph Aevrin builds
itself, which is a smaller, weaker, but honest claim for later work to add
alongside this, never instead of it.

Needs no network at all, unlike SemgrepAdapter: the rules are local files,
never fetched from Semgrep's registry.
"""

from __future__ import annotations

import json
import os
from uuid import UUID

from ..classification.owasp import OwaspMcpCategory
from ..execution.paths import relative_to_mount
from ..execution.runner import DockerRunSpec, LocalCommandSpec
from ..execution.semgrep_ignore import ensure_no_default_semgrepignore
from ..models import Finding, Location, Severity, ToolName
from .base import ScannerAdapter

_SEVERITY_MAP = {
    "ERROR": Severity.HIGH,
    "WARNING": Severity.MEDIUM,
    "INFO": Severity.LOW,
}

# aevrin_scanner_core/adapters/mcp_behavior.py -> aevrin_scanner_core/rules/mcp
# An editable install (how backend/api and backend/cli both depend on this
# package, in development and in the production image alike - see
# backend/api/Dockerfile) redirects straight back to this source tree, so
# this path resolves the same way in every deployment.
RULES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rules", "mcp")
_RULES_DIR_IN_CONTAINER = "/aevrin-mcp-rules"

# A rule shipped without valid aevrin-owasp metadata is an authoring bug in
# Aevrin's own pack. That is never a reason to drop real evidence a taint
# rule already fired on - file it under the closest generic bucket instead
# of silently discarding the finding.
_FALLBACK_CATEGORY = OwaspMcpCategory.EXCESSIVE_AGENCY


class McpBehaviorAdapter(ScannerAdapter):
    tool = ToolName.AEVRIN_MCP_BEHAVIOR

    def build_spec(self, target_dir: str) -> DockerRunSpec:
        return DockerRunSpec(
            image="semgrep/semgrep:1.172.0",
            args=["semgrep", "scan", "--config", _RULES_DIR_IN_CONTAINER, "--json", "--metrics=off", "/src"],
            mounts={
                target_dir: ("/src", True),
                RULES_DIR: (_RULES_DIR_IN_CONTAINER, True),
            },
            workdir="/src",
            network_enabled=False,
            timeout_s=90,
            ok_exit_codes=(0,),
        )

    def build_local_command(self, target_dir: str) -> LocalCommandSpec:
        return LocalCommandSpec(
            binary="semgrep",
            args=["scan", "--config", RULES_DIR, "--json", "--metrics=off", "."],
            timeout_s=90,
            ok_exit_codes=(0,),
        )

    def run(self, scan_id: UUID, target_dir: str) -> list[Finding]:
        # See execution/semgrep_ignore.py: without this, Semgrep's own
        # default ignore patterns silently skip any path in the target
        # containing a directory literally named "tests" (and similar) -
        # exactly the shape a real tool registration could live under.
        ensure_no_default_semgrepignore(target_dir)
        return super().run(scan_id, target_dir)

    def parse_output(self, scan_id: UUID, stdout: str) -> list[Finding]:
        data = json.loads(stdout)
        findings: list[Finding] = []
        for result in data.get("results", []):
            extra = result.get("extra", {})
            metadata = extra.get("metadata", {})
            capability = str(metadata.get("aevrin-capability") or "unknown_capability")
            owasp_raw = str(metadata.get("aevrin-owasp") or "")
            try:
                owasp_category = OwaspMcpCategory(owasp_raw)
            except ValueError:
                owasp_category = _FALLBACK_CATEGORY
            severity = _SEVERITY_MAP.get(extra.get("severity", "WARNING"), Severity.MEDIUM)
            # Loading rules from a directory (rather than a single named
            # ruleset) makes Semgrep prefix check_id with the whole
            # filesystem path to the rule pack, which is a deployment
            # detail, not part of the rule's identity - only the part after
            # the last "." is the id this pack actually defines.
            check_id = str(result.get("check_id", "")).rsplit(".", 1)[-1] or "mcp-behavior"
            label = capability.replace("_", " ")
            findings.append(
                Finding(
                    scan_id=scan_id,
                    tool=self.tool,
                    owasp_category=owasp_category,
                    severity=severity,
                    title=f"MCP tool input reaches {label}",
                    description=extra.get("message", f"{check_id}: {label}"),
                    location=Location(
                        file_path=relative_to_mount(result.get("path")),
                        line_start=result.get("start", {}).get("line"),
                        line_end=result.get("end", {}).get("line"),
                    ),
                    remediation=(
                        f"Confirm this tool actually needs {label} to fulfil its declared "
                        "purpose. If it does, document that scope explicitly; if it doesn't, "
                        "remove the capability rather than leaving it reachable from tool input."
                    ),
                    capability=capability,
                    raw=result,
                )
            )
        return findings
