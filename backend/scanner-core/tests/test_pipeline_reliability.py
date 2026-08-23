"""Regression coverage for a live-reproduced bug: when Docker isn't running
(or a binary is missing, or the network is down), every scanner tool fails
silently, and an empty findings list is indistinguishable from "nothing
found" unless tracked explicitly. A scan in that state must never present as
a clean 100/100 result; see Scan.unreliable_stages / ScanStatus.INCOMPLETE.
"""

from __future__ import annotations

import json
from uuid import uuid4

from aevrin_scanner_core.execution.runner import ToolExecutionError
from aevrin_scanner_core.models import ScanStatus, StageName, StageStatus, TargetType
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
