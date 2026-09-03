"""Regression coverage for a live-reproduced bug: when Docker isn't running
(or a binary is missing, or the network is down), every scanner tool fails
silently, and an empty findings list is indistinguishable from "nothing
found" unless tracked explicitly. A scan in that state must never present as
a clean 100/100 result; see Scan.unreliable_stages / ScanStatus.INCOMPLETE.
"""

from __future__ import annotations

import json
from uuid import uuid4

from aevrin_scanner_core.classification.owasp import OwaspMcpCategory
from aevrin_scanner_core.execution.runner import ToolExecutionError
from aevrin_scanner_core.models import (
    Finding,
    Location,
    ScanStatus,
    Severity,
    StageName,
    StageStatus,
    TargetType,
    ToolName,
)
from aevrin_scanner_core.pipeline import PipelineConfig, run_pipeline
from aevrin_scanner_core.pipeline import orchestrator as pipeline_module


class _FakeAdapter:
    def __init__(self, *, error: Exception | None = None):
        self._error = error

    def run(self, scan_id, target_dir):
        if self._error:
            raise self._error
        return []


def _patch_core_adapters(monkeypatch, *, failing: frozenset[str] = frozenset()):
    """Every tool pipeline.py can invoke for a LOCAL_PATH target, faked to
    either succeed with zero findings or raise ToolExecutionError, like a
    missing binary / unreachable Docker daemon would."""

    def factory(label: str):
        if label in failing:
            return lambda *a, **k: _FakeAdapter(
                error=ToolExecutionError(label, "docker CLI not found on host")
            )
        return lambda *a, **k: _FakeAdapter()

    for attr, label in (
        ("SemgrepAdapter", "semgrep"),
        ("BanditAdapter", "bandit"),
        ("GitleaksAdapter", "gitleaks"),
        ("TruffleHogAdapter", "trufflehog"),
        ("OsvScannerAdapter", "osv-scanner"),
        ("TrivyAdapter", "trivy"),
    ):
        monkeypatch.setattr(pipeline_module, attr, factory(label))


def _noop_stage(stage) -> None:
    pass


def _noop_findings(findings) -> None:
    pass


def _run(tmp_path):
    return run_pipeline(
        TargetType.LOCAL_PATH,
        str(tmp_path),
        PipelineConfig(),
        _noop_stage,
        _noop_findings,
        scan_id=uuid4(),
    )


def test_all_tools_succeeding_is_completed_not_incomplete(monkeypatch, tmp_path):
    _patch_core_adapters(monkeypatch, failing=frozenset())
    scan = _run(tmp_path)
    assert scan.status == ScanStatus.COMPLETED
    assert scan.unreliable_stages == []
    assert scan.score == 100


def test_scan_components_reach_the_scan_object_end_to_end(monkeypatch, tmp_path):
    """Not about reliability - reuses this file's LOCAL_PATH harness to pin
    that Scan.mcp_components is actually populated by the real pipeline run,
    not just by the underlying detect_mcp_server() unit tested in isolation
    in test_mcp_detection.py."""
    _patch_core_adapters(monkeypatch, failing=frozenset())
    (tmp_path / "mcp-server").mkdir()
    (tmp_path / "mcp-server" / "package.json").write_text(
        '{"dependencies": {"@modelcontextprotocol/sdk": "^1.30.0"}}'
    )
    (tmp_path / "mcp-server" / "index.ts").write_text(
        'import { Server } from "@modelcontextprotocol/sdk/server";\nconst s = new Server({});\n'
    )
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text('{"dependencies": {"react": "^18.0.0"}}')

    scan = _run(tmp_path)

    assert [c["root"] for c in scan.mcp_components] == ["mcp-server"]
    assert scan.mcp_components[0]["confidence"] == "high"


def test_mcp_analysis_stage_runs_and_joins_findings_to_their_tool(monkeypatch, tmp_path):
    """The end-to-end wiring test for StageName.MCP_ANALYSIS: a fake
    McpBehaviorAdapter finding at the real sink's line reaches scan.findings
    with mcp_tool set, via the real capability_map.attribute_findings_to_tools
    call inside the real orchestrator - not just the adapter/join units
    tested in isolation elsewhere. McpBehaviorAdapter itself is faked (never
    invokes real Semgrep) for the same portability reason every other
    adapter in this file's tests is."""
    _patch_core_adapters(monkeypatch, failing=frozenset())
    (tmp_path / "server.py").write_text(
        "from mcp.server import FastMCP\n"                  # line 1: sdk_import signal
        "@mcp.tool()\n"                                       # line 2: registration signal
        "def run_command(command: str) -> str:\n"            # line 3
        '    """Run a shell command."""\n'                    # line 4
        "    return subprocess.run(command, shell=True)\n"   # line 5: the sink
    )
    # sdk_import + registration is enough for detect_mcp_server to reach at
    # least "medium" confidence, which is what gates discover_tools() being
    # called at all in the real orchestrator - a fixture scoring "none"
    # would make this test pass for the wrong reason (the SKIPPED branch),
    # not the one it names.

    class _FakeMcpBehaviorAdapter:
        def run(self, scan_id, target_dir):
            return [
                Finding(
                    scan_id=scan_id,
                    tool=ToolName.AEVRIN_MCP_BEHAVIOR,
                    owasp_category=OwaspMcpCategory.EXCESSIVE_AGENCY,
                    severity=Severity.HIGH,
                    title="MCP tool input reaches shell execution",
                    description="d",
                    location=Location(file_path="server.py", line_start=5, line_end=5),
                    remediation="r",
                )
            ]

    monkeypatch.setattr(pipeline_module, "McpBehaviorAdapter", lambda: _FakeMcpBehaviorAdapter())

    scan = _run(tmp_path)

    mcp_stage = next(s for s in scan.stages if s.name == StageName.MCP_ANALYSIS)
    assert mcp_stage.status == StageStatus.DONE
    behavior_findings = [f for f in scan.findings if f.tool == ToolName.AEVRIN_MCP_BEHAVIOR]
    assert len(behavior_findings) == 1
    assert behavior_findings[0].mcp_tool == "run_command"


def test_mcp_analysis_stage_is_skipped_when_no_tools_are_declared(monkeypatch, tmp_path):
    """No @mcp.tool() anywhere in this target - nothing for the behavior
    pack to check arguments against, so the stage is SKIPPED rather than
    invoking the adapter (or claiming DONE) over an empty tool list."""
    _patch_core_adapters(monkeypatch, failing=frozenset())
    (tmp_path / "app.py").write_text("print('hello')\n")

    called = False

    class _ShouldNeverRun:
        def run(self, scan_id, target_dir):
            nonlocal called
            called = True
            return []

    monkeypatch.setattr(pipeline_module, "McpBehaviorAdapter", lambda: _ShouldNeverRun())

    scan = _run(tmp_path)

    mcp_stage = next(s for s in scan.stages if s.name == StageName.MCP_ANALYSIS)
    assert mcp_stage.status == StageStatus.SKIPPED
    assert called is False


def _write_run_command_server(tmp_path) -> None:
    (tmp_path / "server.py").write_text(
        "from mcp.server import FastMCP\n"
        "@mcp.tool()\n"
        "def run_command(command: str) -> str:\n"
        '    """Run a shell command."""\n'
        "    return subprocess.run(command, shell=True)\n"
    )


def test_scan_mcp_capabilities_reflects_declared_tools(monkeypatch, tmp_path):
    """capability_summary() was computed by mcp_detection.py and immediately
    discarded before this - nothing captured its result on Scan. A
    repository declaring an executing tool must produce can_execute: True
    here, not just in the standalone capability_summary() unit tests."""
    _patch_core_adapters(monkeypatch, failing=frozenset())
    _write_run_command_server(tmp_path)

    scan = _run(tmp_path)

    assert scan.mcp_capabilities is not None
    assert scan.mcp_capabilities["can_execute"] is True


def test_scan_mcp_capabilities_is_none_when_tool_discovery_never_ran(monkeypatch, tmp_path):
    """A target with no MCP evidence at all must report 'never established',
    not 'established as no capabilities' - the two are different claims and
    only this distinguishes them for the marketplace grade."""
    _patch_core_adapters(monkeypatch, failing=frozenset())
    (tmp_path / "app.py").write_text("print('hello')\n")

    scan = _run(tmp_path)

    assert scan.mcp_capabilities is None


def test_tool_signature_pins_change_when_description_changes():
    from aevrin_scanner_core.analysis.mcp_detection import DiscoveredTool

    before = pipeline_module._tool_signature_pins(
        [DiscoveredTool(name="run_command", description="Runs a command", file_path="s.py")]
    )
    after = pipeline_module._tool_signature_pins(
        [DiscoveredTool(name="run_command", description="Runs anything, unrestricted", file_path="s.py")]
    )
    assert before[0].server_name == after[0].server_name == "tool:run_command"
    assert before[0].signature_hash != after[0].signature_hash


def test_tool_signature_pins_unaffected_by_line_range_shifting():
    from aevrin_scanner_core.analysis.mcp_detection import DiscoveredTool

    a = pipeline_module._tool_signature_pins(
        [DiscoveredTool(name="run_command", description="d", file_path="s.py", line_start=2, line_end=4)]
    )
    b = pipeline_module._tool_signature_pins(
        [DiscoveredTool(name="run_command", description="d", file_path="s.py", line_start=40, line_end=44)]
    )
    assert a[0].signature_hash == b[0].signature_hash


def test_source_rug_pull_fires_when_a_declared_tool_changes(monkeypatch, tmp_path):
    """The static counterpart to the live-connection rug-pull diff: a
    repository's own declared tool surface can drift between scans of the
    same target too, and a fresh clone every scan means there's no local
    pin state to lean on the way a real MCP client has."""
    _patch_core_adapters(monkeypatch, failing=frozenset())
    _write_run_command_server(tmp_path)

    stale_hash = "0" * 64  # deliberately wrong, standing in for "last scan's hash"
    config = PipelineConfig(previous_signatures={"tool:run_command": stale_hash})
    scan = run_pipeline(
        TargetType.LOCAL_PATH, str(tmp_path), config, _noop_stage, _noop_findings, scan_id=uuid4()
    )

    rug_pull_findings = [f for f in scan.findings if f.owasp_category == OwaspMcpCategory.RUG_PULL]
    assert len(rug_pull_findings) == 1
    assert "run_command" in rug_pull_findings[0].title
    # The fresh hash for this scan is what gets persisted for next time - the
    # caller (services/scan.py) reads this straight off the config afterward.
    assert any(key == "tool:run_command" and h != stale_hash for key, h in config.computed_signatures)


def test_source_rug_pull_silent_on_first_scan_of_a_target(monkeypatch, tmp_path):
    """No previous_signatures at all - the common case, a target's first
    scan - must never manufacture a drift finding out of nothing."""
    _patch_core_adapters(monkeypatch, failing=frozenset())
    _write_run_command_server(tmp_path)

    scan = _run(tmp_path)

    assert [f for f in scan.findings if f.owasp_category == OwaspMcpCategory.RUG_PULL] == []


def test_docker_down_scenario_never_reports_clean(monkeypatch, tmp_path):
    """The exact bug: every tool fails (simulating Docker daemon down);
    previously this still produced a 100/100 'Clean' scan."""
    _patch_core_adapters(
        monkeypatch,
        failing=frozenset({"semgrep", "bandit", "gitleaks", "trufflehog", "osv-scanner", "trivy"}),
    )
    scan = _run(tmp_path)
    assert scan.status == ScanStatus.INCOMPLETE
    assert set(scan.unreliable_stages) == {
        StageName.STATIC_ANALYSIS,
        StageName.SECRETS,
        StageName.DEPENDENCIES,
    }


def test_one_category_fully_failing_marks_only_that_stage_unreliable(monkeypatch, tmp_path):
    _patch_core_adapters(monkeypatch, failing=frozenset({"semgrep", "bandit"}))
    scan = _run(tmp_path)
    assert scan.status == ScanStatus.INCOMPLETE
    assert scan.unreliable_stages == [StageName.STATIC_ANALYSIS]


def test_partial_failure_within_a_stage_still_counts_as_reliable(monkeypatch, tmp_path):
    """One of two tools in a category failing shouldn't taint the whole
    category, the other tool still provided real coverage."""
    _patch_core_adapters(monkeypatch, failing=frozenset({"semgrep"}))
    scan = _run(tmp_path)
    assert scan.status == ScanStatus.COMPLETED
    assert scan.unreliable_stages == []


def test_missing_mcp_entrypoint_is_skipped_not_failed(monkeypatch, tmp_path):
    _patch_core_adapters(monkeypatch, failing=frozenset())
    scan = _run(tmp_path)

    stage = next(s for s in scan.stages if s.name == StageName.TOOL_DESCRIPTION_CHECK)
    assert stage.status == StageStatus.SKIPPED
    assert "not applicable" in (stage.error or "").lower()


def test_stdio_mcp_entry_is_never_executed(monkeypatch):
    class _MustNotRun:
        def run(self, *args, **kwargs):
            raise AssertionError("untrusted stdio command was executed")

    monkeypatch.setattr(pipeline_module, "McpShieldAdapter", _MustNotRun)
    target = json.dumps(
        {"mcpServers": {"untrusted": {"command": "sh", "args": ["-c", "do-bad-things"]}}}
    )

    scan = run_pipeline(
        TargetType.CONFIG_PASTE,
        target,
        PipelineConfig(),
        _noop_stage,
        _noop_findings,
        scan_id=uuid4(),
    )

    stage = next(s for s in scan.stages if s.name == StageName.TOOL_DESCRIPTION_CHECK)
    assert stage.status == StageStatus.SKIPPED
    assert "never executes submitted stdio commands" in (stage.error or "")


def test_live_server_capabilities_reach_the_scan_end_to_end(monkeypatch):
    """The other end of the live-handshake wiring: before this,
    Scan.mcp_capabilities was always None for a live/pasted-config target -
    there was no source for discover_tools() to read, and nothing rolled
    mcp-shield's live tool descriptions into a capability summary the way
    the source-repo path already did (see DECISIONS.md's ADR on this).
    This drives run_pipeline for real (not just inspect_remote_signatures in
    isolation, tested elsewhere) with a fake handshake standing in for the
    real network call."""
    import socket
    from contextlib import asynccontextmanager

    from aevrin_scanner_core.analysis import remote_mcp as remote_mcp_module

    class _FakeTool:
        def __init__(self, name: str, description: str):
            self._name, self._description = name, description

        def model_dump(self, mode="json", exclude_none=True):
            return {"name": self._name, "description": self._description}

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def initialize(self):
            return None

        async def list_tools(self):
            class _Response:
                def __init__(self):
                    self.tools = [_FakeTool("run_command", "Executes an arbitrary shell command")]

            return _Response()

    @asynccontextmanager
    async def fake_streamable_http_client(url, http_client):
        yield (object(), object(), None)

    monkeypatch.setattr(remote_mcp_module, "streamable_http_client", fake_streamable_http_client)
    monkeypatch.setattr(remote_mcp_module, "ClientSession", lambda read, write: _FakeSession())
    monkeypatch.setattr(pipeline_module, "McpShieldAdapter", lambda: _FakeAdapter())
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )

    target = json.dumps({"mcpServers": {"acme": {"url": "https://mcp.example.com/mcp"}}})
    scan = run_pipeline(
        TargetType.CONFIG_PASTE, target, PipelineConfig(), _noop_stage, _noop_findings, scan_id=uuid4()
    )

    assert scan.mcp_capabilities is not None
    assert scan.mcp_capabilities["can_execute"] is True


def _stage(scan, name):
    return next(s for s in scan.stages if s.name == name)


def test_both_dependency_scanners_failing_marks_the_stage_failed(monkeypatch, tmp_path):
    """The stage's verdict must come from the tools that decide whether the
    category was covered.

    openssf-scorecard was counted in the failure threshold, making it 3 for a
    stage whose own logic already excludes scorecard from that judgement. With
    osv-scanner and trivy both dead that was 2 failures against a threshold of
    3, so the stage reported success: a green dependencies stage with no
    dependency scanning behind it.
    """
    _patch_core_adapters(monkeypatch, failing=frozenset({"osv-scanner", "trivy"}))
    scan = _run(tmp_path)

    stage = _stage(scan, StageName.DEPENDENCIES)
    assert stage.status == StageStatus.FAILED
    # And the two halves of the report must agree with each other. They did
    # not: the stage said done while the summary listed it as unrunnable.
    assert StageName.DEPENDENCIES in scan.unreliable_stages
    assert scan.status == ScanStatus.INCOMPLETE


def test_scorecard_being_unconfigured_is_a_notice_not_a_failure(monkeypatch, tmp_path):
    """Not asking a tool to run is not the same as it breaking. Without a
    GITHUB_TOKEN, scorecard is simply out of scope for the run."""
    _patch_core_adapters(monkeypatch)
    scan = _run(tmp_path)

    stage = _stage(scan, StageName.DEPENDENCIES)
    assert stage.status == StageStatus.DONE
    assert StageName.DEPENDENCIES not in scan.unreliable_stages
    # Still reported -- a silently absent check is the thing this scanner
    # refuses to do -- but it must not be what decides the stage's verdict.
    assert "openssf-scorecard: skipped" in (stage.error or "")


def test_one_dependency_scanner_failing_still_leaves_the_category_covered(monkeypatch, tmp_path):
    """osv-scanner alone is real coverage, so this is not INCOMPLETE -- but
    the failure has to remain visible on the stage rather than vanishing."""
    _patch_core_adapters(monkeypatch, failing=frozenset({"trivy"}))
    scan = _run(tmp_path)

    stage = _stage(scan, StageName.DEPENDENCIES)
    assert stage.status == StageStatus.DONE
    assert StageName.DEPENDENCIES not in scan.unreliable_stages
    assert "trivy" in (stage.error or "")
