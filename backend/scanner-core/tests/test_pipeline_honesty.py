"""What the pipeline must never do: present an unassessed server as a safe one.

Every test here is one way a scan can fail. None of them may end with a
letter grade, a risk score, or a completed status - because a completed scan
with zero findings is indistinguishable from a clean server, and that
indistinguishability is the failure this product exists to avoid.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aevrin_scanner_core.mcp import tooltrust
from aevrin_scanner_core.mcp.tooltrust import ScanReport, ServerLaunchError
from aevrin_scanner_core.models import ScanStatus, StageName, StageStatus, TargetType
from aevrin_scanner_core.pipeline.orchestrator import PipelineConfig, run_pipeline

FIXTURES = Path(__file__).parent / "fixtures" / "scanner"


def run(monkeypatch, *, target_type=TargetType.LIVE_MCP_SERVER, target="npx -y demo", scan=None):
    if scan is not None:
        monkeypatch.setattr(tooltrust, "scan_live_server", scan)
        monkeypatch.setattr(
            "aevrin_scanner_core.pipeline.orchestrator.scan_live_server", scan
        )
    return run_pipeline(
        target_type,
        target,
        PipelineConfig(),
        on_stage=lambda _s: None,
        on_findings=lambda _f: None,
    )


def report_from(name: str, scan_id):
    return tooltrust.parse_report(
        json.loads((FIXTURES / name).read_text(encoding="utf-8")), scan_id=scan_id
    )


# --------------------------------------------------------------- happy path


def test_a_successful_scan_carries_the_engine_verdict(monkeypatch) -> None:
    def fake(command, *, scan_id):
        return report_from("exec-cases.scan.json", scan_id)

    scan = run(monkeypatch, scan=fake)

    assert scan.status is ScanStatus.COMPLETED
    assert scan.grade == "C"
    assert scan.risk_score == 27
    assert len(scan.mcp_tools_declared) == 6
    assert scan.mcp_detected is True
    assert all(s.status is StageStatus.DONE for s in scan.stages)


def test_the_command_actually_run_is_recorded(monkeypatch) -> None:
    """A grade attributed to the wrong package is worse than no grade, so the
    command that produced it is stored with the result."""
    seen: list[str] = []

    def fake(command, *, scan_id):
        seen.append(command)
        return report_from("clean.scan.json", scan_id)

    scan = run(monkeypatch, target="npx -y @playwright/mcp", scan=fake)
    assert seen == ["npx -y @playwright/mcp"]
    assert scan.server_command == "npx -y @playwright/mcp"
    assert scan.scanner_version


def test_findings_are_grouped_before_they_are_shown(monkeypatch) -> None:
    """AS-014 fires on every tool. Six identical cards is how the finding that
    matters gets scrolled past."""

    def fake(command, *, scan_id):
        return report_from("exec-cases.scan.json", scan_id)

    scan = run(monkeypatch, scan=fake)
    as014 = [f for f in scan.findings if f.rule_id == "AS-014"]
    assert len(as014) == 1
    assert as014[0].occurrence_count == 6
    assert len(as014[0].affected_tools) == 6


# ------------------------------------------------------------- the failures


def test_a_server_that_will_not_launch_is_incomplete_not_clean(monkeypatch) -> None:
    def fake(command, *, scan_id):
        raise ServerLaunchError("npm ERR! 404 Not Found")

    scan = run(monkeypatch, scan=fake)

    assert scan.status is ScanStatus.INCOMPLETE
    assert scan.grade is None
    assert scan.risk_score is None
    launching = next(s for s in scan.stages if s.name is StageName.LAUNCHING)
    assert launching.status is StageStatus.FAILED
    assert "could not be launched" in (launching.error or "")


def test_a_server_exposing_no_tools_is_not_a_clean_server(monkeypatch) -> None:
    def fake(command, *, scan_id):
        return ScanReport(
            tools=(), policies=(), findings=[], risk_score=None, grade=None,
            policy=tooltrust.Policy.REQUIRE_APPROVAL,
        )

    scan = run(monkeypatch, scan=fake)

    assert scan.status is ScanStatus.INCOMPLETE
    assert scan.grade is None
    enumerating = next(s for s in scan.stages if s.name is StageName.ENUMERATING)
    assert enumerating.status is StageStatus.FAILED
    assert "nothing to assess" in (enumerating.error or "")


def test_unreadable_engine_output_never_becomes_a_clean_result(monkeypatch) -> None:
    def fake(command, *, scan_id):
        raise tooltrust.ScannerOutputError("truncated JSON")

    scan = run(monkeypatch, scan=fake)

    assert scan.status is ScanStatus.INCOMPLETE
    assert scan.grade is None


def test_a_repository_with_no_launchable_package_stops_at_resolving(tmp_path: Path) -> None:
    """The non-MCP repository case. It ends honestly at the first stage
    rather than falling back to scanning source files for something to say."""
    repo = tmp_path / "not-an-mcp-server"
    repo.mkdir()
    (repo / "README.md").write_text("just a project", encoding="utf-8")

    scan = run_pipeline(
        TargetType.LOCAL_PATH, str(repo), PipelineConfig(),
        on_stage=lambda _s: None, on_findings=lambda _f: None,
    )

    assert scan.status is ScanStatus.INCOMPLETE
    assert scan.grade is None
    assert scan.mcp_detected is False
    assert scan.findings == []
    resolving = next(s for s in scan.stages if s.name is StageName.RESOLVING)
    assert resolving.status is StageStatus.FAILED
    later = [s for s in scan.stages if s.name is not StageName.RESOLVING]
    assert all(s.status is StageStatus.SKIPPED for s in later)


def test_an_explicit_command_overrides_repository_resolution(tmp_path: Path, monkeypatch) -> None:
    """The user telling us how to start their server is better evidence than
    a manifest, so it wins."""
    seen: list[str] = []

    def fake(command, *, scan_id):
        seen.append(command)
        return report_from("clean.scan.json", scan_id)

    monkeypatch.setattr("aevrin_scanner_core.pipeline.orchestrator.scan_live_server", fake)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text(
        json.dumps({"name": "@scope/from-manifest", "bin": {"x": "x.js"}}), encoding="utf-8"
    )

    run_pipeline(
        TargetType.LOCAL_PATH, str(repo),
        PipelineConfig(server_command="npx -y @scope/explicit"),
        on_stage=lambda _s: None, on_findings=lambda _f: None,
    )
    assert seen == ["npx -y @scope/explicit"]


@pytest.mark.parametrize(
    "name", [StageName.RESOLVING, StageName.LAUNCHING, StageName.ENUMERATING]
)
def test_every_failure_stage_names_a_reason(monkeypatch, name: StageName) -> None:
    """"Scan incomplete" with no explanation is not actionable."""
    failures = {
        StageName.RESOLVING: (TargetType.CONFIG_PASTE, None),
        StageName.LAUNCHING: (
            TargetType.LIVE_MCP_SERVER,
            lambda command, *, scan_id: (_ for _ in ()).throw(ServerLaunchError("boom")),
        ),
        StageName.ENUMERATING: (
            TargetType.LIVE_MCP_SERVER,
            lambda command, *, scan_id: ScanReport(
                tools=(), policies=(), findings=[], risk_score=None, grade=None,
                policy=tooltrust.Policy.REQUIRE_APPROVAL,
            ),
        ),
    }
    target_type, fake = failures[name]
    scan = run(monkeypatch, target_type=target_type, scan=fake)

    failed = next(s for s in scan.stages if s.status is StageStatus.FAILED)
    assert failed.name is name
    assert failed.error and len(failed.error) > 20
    assert scan.grade is None


def test_a_launch_failure_message_is_diagnostic_without_naming_the_engine() -> None:
    """Found by running the real thing, not by reading the code.

    A live scan of a package that does not exist ended with the engine's
    entire flag list pasted into the stage error a user reads - the binary
    name, every option, and a mojibake character where a tail-truncated
    excerpt had cut a UTF-8 sequence in half. Two failures at once: §21 says
    a user is never told which engine produced their scan, and the actual
    cause was the one part that got dropped, because `ToolExecutionError`
    keeps the *last* 600 characters and the manual is longer than that.
    """
    stderr = (
        "Error: live server scan failed (or timed out): initialization failed: "
        "transport error: transport closed\n"
        "Usage:\n"
        "  mcp-scanner scan [flags]\n"
        "\n"
        "Examples:\n"
        "  mcp-scanner scan --server 'npx -y pkg'\n"
        "Flags:\n"
        "  -o, --output string   output format: text (default) | json\n"
        "  -s, --server string   live MCP server to scan\n"
    )
    reason = tooltrust._launch_reason(stderr, "fallback")

    assert "transport closed" in reason, "the actual cause must survive"
    for leaked in ("tooltrust", "--output", "--server", "[flags]"):
        assert leaked not in reason, f"{leaked!r} reached a user-facing message"


def test_a_launch_failure_with_nothing_to_say_still_says_something() -> None:
    """Empty stderr must not produce an empty reason: "scan incomplete" with
    a blank explanation is the non-actionable message this all exists to
    avoid."""
    assert tooltrust._launch_reason("", "the server exited early") == "the server exited early"
    assert tooltrust._launch_reason("   \n\n  ", "the server exited early") == "the server exited early"


def test_aevrins_own_image_name_survives_redaction() -> None:
    """The redaction guards upstream's identity, not the word "scanner".

    `mcp-scanner` is Aevrin's own name - the sandbox image installs the release
    binary as /usr/local/bin/mcp-scanner and is tagged aevrin/mcp-scanner - so
    stripping it carried no §21 benefit and cost the only actionable fact in
    the most common deployment failure. It read:

        Unable to find image 'aevrin/the scan engine:0.3.19' locally

    which names an image that cannot exist, for an operator whose actual
    problem is that they have not built one that can.
    """
    stderr = (
        "Unable to find image 'aevrin/mcp-scanner:0.3.19' locally\n"
        "docker: Error response from daemon: pull access denied for aevrin/mcp-scanner\n"
    )
    reason = tooltrust._launch_reason(stderr, "fallback")

    assert "aevrin/mcp-scanner:0.3.19" in reason
    assert "the scan engine" not in reason
