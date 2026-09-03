"""McpBehaviorAdapter.parse_output, against Semgrep's real JSON shape.

The rule pack itself (rules/mcp/*.yaml) was verified empirically against
real Semgrep 1.174.0 during development - a tainted MCP tool argument
reaching subprocess/filesystem/network/credential sinks fires exactly
once at the sink's own line, a safe twin with the same shape does not fire
at all, and a tool that calls a helper function which contains the sink
does not fire either (Semgrep's open-source engine is intra-procedural
only - see the module's own docstring). That verification is not
automated here: running the real binary against fixtures would make this
suite depend on Semgrep being installed and behaving identically across
versions, which every other adapter test in this file avoids by testing
parse_output against a captured JSON shape instead. This file follows the
same convention; test_rules_dir_exists_and_is_shipped is what stays
portable without the binary.
"""

from __future__ import annotations

import json
import os
from uuid import uuid4

from aevrin_scanner_core.adapters.mcp_behavior import RULES_DIR, McpBehaviorAdapter
from aevrin_scanner_core.classification.owasp import OwaspMcpCategory
from aevrin_scanner_core.models import Severity


def _result(
    *,
    rule_id: str = "mcp-tool-input-reaches-shell",
    capability: str = "shell_execution",
    owasp: str = "MCP09",
    severity: str = "ERROR",
    path: str = "server.py",
    line: int = 8,
) -> dict:
    # Exact shape captured from a real `semgrep scan --config rules/mcp
    # --json` run, loading rules from a directory rather than a single
    # named ruleset - which is why check_id carries the whole filesystem
    # path to the pack ahead of the rule's own id.
    return {
        "check_id": f"B.some.host.path.to.rules.mcp.{rule_id}",
        "path": path,
        "start": {"line": line, "col": 1, "offset": 0},
        "end": {"line": line, "col": 10, "offset": 9},
        "extra": {
            "message": "An MCP tool argument reaches a dangerous sink.",
            "metadata": {"aevrin-capability": capability, "aevrin-owasp": owasp},
            "severity": severity,
        },
    }


def test_rules_dir_exists_and_is_shipped():
    """If this fails, the adapter's --config points at a directory that
    does not exist in this deployment - see the module docstring on why an
    editable install is what makes the path resolve the same way in dev and
    in the production image."""
    assert os.path.isdir(RULES_DIR)
    assert sorted(os.listdir(RULES_DIR)) == [
        "credentials.yaml",
        "filesystem.yaml",
        "network.yaml",
        "shell_execution.yaml",
    ]


def test_check_id_directory_prefix_is_stripped_for_the_title():
    output = json.dumps({"results": [_result()]})
    (finding,) = McpBehaviorAdapter().parse_output(uuid4(), output)
    assert finding.title == "MCP tool input reaches shell execution"


def test_category_and_capability_come_from_rule_metadata_not_a_hardcoded_bucket():
    """The defect this whole adapter exists to avoid: SemgrepAdapter files
    every finding under one OWASP category regardless of what the rule
    actually found. Each rule here carries its own."""
    output = json.dumps(
        {
            "results": [
                _result(rule_id="mcp-tool-handler-reads-credential-path", capability="credential_access", owasp="MCP01"),
                _result(rule_id="mcp-tool-input-reaches-network-request", capability="network_outbound", owasp="MCP05"),
            ]
        }
    )
    findings = McpBehaviorAdapter().parse_output(uuid4(), output)
    assert findings[0].owasp_category == OwaspMcpCategory.TOKEN_MISMANAGEMENT
    assert findings[1].owasp_category == OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF


def test_severity_map_matches_semgrep_convention():
    output = json.dumps({"results": [_result(severity="WARNING")]})
    (finding,) = McpBehaviorAdapter().parse_output(uuid4(), output)
    assert finding.severity == Severity.MEDIUM


def test_a_rule_with_no_valid_owasp_metadata_still_produces_a_finding():
    """An authoring bug in Aevrin's own pack must never cost real evidence
    a taint rule already fired on - see _FALLBACK_CATEGORY."""
    output = json.dumps({"results": [_result(owasp="not-a-real-category")]})
    (finding,) = McpBehaviorAdapter().parse_output(uuid4(), output)
    assert finding.owasp_category == OwaspMcpCategory.EXCESSIVE_AGENCY


def test_location_and_raw_are_preserved():
    output = json.dumps({"results": [_result(path="mcp-server/handlers.py", line=42)]})
    (finding,) = McpBehaviorAdapter().parse_output(uuid4(), output)
    assert finding.location.file_path == "mcp-server/handlers.py"
    assert finding.location.line_start == 42
    assert finding.raw is not None


def test_run_writes_semgrepignore_into_the_target_before_scanning(monkeypatch, tmp_path):
    """Without this, Semgrep's own default ignore patterns would silently
    skip any tests-named directory in the actual target being scanned -
    see execution/semgrep_ignore.py and DECISIONS.md ADR-025/026. The
    underlying Semgrep invocation is faked (never invokes a real binary,
    the same convention this whole file follows), but the file write
    itself is real."""
    from aevrin_scanner_core.adapters import base as base_module

    monkeypatch.setattr(base_module, "resolve_execution", lambda *a, **k: "subprocess")
    monkeypatch.setattr(base_module, "run_local_command", lambda *a, **k: ('{"results": []}', "", 0))

    McpBehaviorAdapter().run(uuid4(), str(tmp_path))

    assert (tmp_path / ".semgrepignore").exists()
