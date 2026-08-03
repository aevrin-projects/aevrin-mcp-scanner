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

from aevrin_cli.upload import _serialize_scan


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
    assert payload["findings"][0]["created_at"] == finding.created_at.isoformat()
    assert payload["findings"][0]["raw"] is None
