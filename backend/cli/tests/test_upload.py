from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from aevrin_scanner_core import (
    Finding,
    Location,
    OwaspMcpCategory,
    Scan,
    ScanStage,
    ScanStatus,
    Severity,
    StageName,
    StageStatus,
    TargetType,
    ToolName,
)

from aevrin_cli.services.upload import _serialize_scan


def test_cli_upload_contract_preserves_dashboard_fields() -> None:
    started = datetime.now(UTC) - timedelta(seconds=73)
    completed = datetime.now(UTC)
    scan_id = uuid4()
    finding = Finding(
        scan_id=scan_id,
        tool=ToolName.SEMGREP,
        owasp_category=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
        severity=Severity.HIGH,
        title="Unsafe command construction",
        description="User input reaches a shell command.",
        location=Location(file_path="server.py", line_start=18, line_end=18),
        mcp_tool="run_command",
        capability="shell_execution",
        remediation="Use an argument array and validate input.",
    )
    stage = ScanStage(
        scan_id=scan_id,
        name=StageName.STATIC_ANALYSIS,
        status=StageStatus.DONE,
        started_at=started,
        finished_at=completed,
    )
    scan = Scan(
        id=scan_id,
        target_type=TargetType.LOCAL_PATH,
        target="/workspace/example-server",
        status=ScanStatus.COMPLETED,
        score=80,
        mcp_detected=True,
        mcp_detection_confidence="high",
        mcp_detection_evidence=["sdk_dependency: depends on fastmcp"],
        mcp_tools_declared=["search"],
        mcp_components=[{"root": ".", "confidence": "high", "evidence": []}],
        mcp_capabilities={"can_execute": False, "can_write": False, "can_read": True,
                          "handles_credentials": False, "makes_network_calls": False},
        stages=[stage],
        findings=[finding],
        created_at=started,
        completed_at=completed,
    )

    payload = _serialize_scan(scan)

    assert payload["scan_id"] == str(scan_id)
    assert payload["target_type"] == "local_path"
    assert payload["created_at"] == started.isoformat()
    assert payload["completed_at"] == completed.isoformat()
    assert payload["stages"][0]["error"] is None
    assert payload["findings"][0]["id"] == str(finding.id)
    assert payload["findings"][0]["file_path"] == "server.py"
    assert payload["findings"][0]["mcp_tool"] == "run_command"
    assert payload["findings"][0]["capability"] == "shell_execution"
    # Discarded before this contract carried them at all - see CHANGELOG.md.
    assert payload["mcp_detection_confidence"] == "high"
    assert payload["mcp_detection_evidence"] == ["sdk_dependency: depends on fastmcp"]
    assert payload["mcp_tools_declared"] == ["search"]
    assert payload["mcp_components"] == [{"root": ".", "confidence": "high", "evidence": []}]
    assert payload["mcp_capabilities"] == {
        "can_execute": False, "can_write": False, "can_read": True,
        "handles_credentials": False, "makes_network_calls": False,
    }
    assert payload["findings"][0]["created_at"] == finding.created_at.isoformat()
    assert payload["findings"][0]["raw"] is None
