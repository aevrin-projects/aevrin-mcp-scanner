"""Regression coverage: /cli/upload must never trust the client-submitted
risk score or grade. Both are recomputed server-side from the submitted
findings using the same shared `grade_scan` the CLI itself used, closing the
cheapest tampering vector - a hand-crafted upload claiming a better letter
than its own findings justify."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from aevrin_scanner_core import grade_scan
from fastapi import BackgroundTasks, HTTPException

from aevrin_api.controllers import cli_controller as cli
from aevrin_api.controllers.cli_controller import _to_core_finding
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.schemas import CliUploadFinding, CliUploadRequest, CliUploadStage


def _finding(severity: str) -> CliUploadFinding:
    return CliUploadFinding(
        id=uuid4(),
        tool="aevrin-mcp-rules",
        owasp_category="MCP05",
        severity=severity,
        title="Example finding",
        description="Example description",
        remediation="Fix it",
    )


def _regrade(findings, scan_id, tools_declared: int = 3):
    return grade_scan(
        [_to_core_finding(f, scan_id) for f in findings],
        coverage_complete=True,
        tools_discovered=tools_declared,
    )


def test_recomputed_risk_ignores_a_falsely_high_client_score():
    """A client claiming "critical, do not use" for a scan that found only
    informational notes."""
    scan_id = uuid4()
    result = _regrade([_finding("info")], scan_id)
    assert result.risk_score == 0
    assert result.grade is not None and result.grade.value == "A"


def test_recomputed_risk_ignores_a_falsely_low_client_score():
    """The dangerous direction: a client hiding a real critical finding."""
    scan_id = uuid4()
    result = _regrade([_finding("critical")], scan_id)
    assert result.risk_score > 0
    assert result.grade is not None and result.grade.value != "A"


def test_a_client_cannot_claim_a_grade_for_a_scan_with_no_tools():
    """A modified CLI reporting an A for a target whose tools it never
    enumerated. The letter is withheld regardless of what was submitted."""
    scan_id = uuid4()
    result = _regrade([_finding("info")], scan_id, tools_declared=0)
    assert result.grade is None
    assert result.incomplete is True


def test_to_core_finding_round_trips_location_fields():
    scan_id = uuid4()
    f = CliUploadFinding(
        id=uuid4(),
        tool="aevrin-mcp-behavior",
        owasp_category="MCP01",
        severity="high",
        title="t",
        description="d",
        file_path="app.py",
        line_start=10,
        line_end=12,
        mcp_tool="run_command",
        capability="shell_execution",
        remediation="r",
    )
    core = _to_core_finding(f, scan_id)
    assert core.scan_id == scan_id
    assert core.location.file_path == "app.py"
    assert core.location.line_start == 10
    assert core.location.line_end == 12
    assert core.mcp_tool == "run_command"
    assert core.capability == "shell_execution"


class _UploadDb:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "scans": [],
            "scan_stages": [],
            "findings": [],
            "hook_cache": [],
        }

    async def select(self, table: str, filters: dict[str, str]) -> list[dict[str, Any]]:
        return [
            row
            for row in self.tables[table]
            if all(str(row.get(key)) == value for key, value in filters.items())
        ]

    async def insert(
        self,
        table: str,
        rows: dict[str, Any] | list[dict[str, Any]],
        *,
        upsert_on: str | None = None,
    ) -> list[dict[str, Any]]:
        incoming = rows if isinstance(rows, list) else [rows]
        if upsert_on:
            conflict_keys = upsert_on.split(",")
            for row in incoming:
                existing = next(
                    (
                        item
                        for item in self.tables[table]
                        if all(item.get(key) == row.get(key) for key in conflict_keys)
                    ),
                    None,
                )
                if existing:
                    existing.update(row)
                else:
                    self.tables[table].append(dict(row))
        else:
            self.tables[table].extend(dict(row) for row in incoming)
        return [dict(row) for row in incoming]

    async def update(
        self, table: str, filters: dict[str, str], patch: dict[str, Any]
    ) -> list[dict[str, Any]]:
        rows = await self.select(table, filters)
        for row in rows:
            row.update(patch)
        return rows


def test_cli_upload_is_idempotent_and_preserves_full_dashboard_record(monkeypatch, settings):
    scan_id = uuid4()
    finding = _finding("critical")
    started = datetime.now(UTC) - timedelta(seconds=68)
    completed = datetime.now(UTC)
    request = CliUploadRequest(
        scan_id=scan_id,
        target_type="local_path",
        target="/workspace/example-server",
        risk_score=60,
        grade="D",
        status="completed",
        created_at=started,
        completed_at=completed,
        mcp_detected=True,
        mcp_detection_confidence="high",
        mcp_detection_evidence=["sdk_dependency: depends on fastmcp"],
        mcp_tools_declared=["search"],
        mcp_components=[{"root": ".", "confidence": "high", "evidence": []}],
        mcp_capabilities={"can_execute": False, "can_write": False, "can_read": True,
                          "handles_credentials": False, "makes_network_calls": False},
        stages=[
            CliUploadStage(
                name="mcp_rules",
                status="done",
                started_at=started,
                finished_at=completed,
            )
        ],
        findings=[finding],
    )
    db = _UploadDb()
    user = AuthenticatedUser("user-1", "developer@example.com")
    quota_calls = 0

    async def fake_quota(*args: Any, **kwargs: Any) -> None:
        nonlocal quota_calls
        quota_calls += 1

    monkeypatch.setattr(cli, "enforce_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "check_and_increment_quota", fake_quota)

    first = asyncio.run(cli.upload_scan(request, BackgroundTasks(), user.id, db, settings))  # type: ignore[arg-type]
    second = asyncio.run(cli.upload_scan(request, BackgroundTasks(), user.id, db, settings))  # type: ignore[arg-type]

    assert first.id == second.id == scan_id
    assert quota_calls == 1
    assert len(db.tables["scans"]) == 1
    assert db.tables["scans"][0]["source"] == "cli"
    assert db.tables["scans"][0]["created_at"] == started.isoformat()
    assert db.tables["scans"][0]["completed_at"] == completed.isoformat()
    # A CLI-local scan's detection confidence/evidence/declared-tools were
    # computed by the pipeline and discarded here before this was wired up -
    # see CHANGELOG.md.
    assert db.tables["scans"][0]["mcp_detection_confidence"] == "high"
    assert db.tables["scans"][0]["mcp_detection_evidence"] == [
        "sdk_dependency: depends on fastmcp"
    ]
    assert db.tables["scans"][0]["mcp_tools_declared"] == ["search"]
    assert db.tables["scans"][0]["mcp_components"] == [
        {"root": ".", "confidence": "high", "evidence": []}
    ]
    assert db.tables["scans"][0]["mcp_capabilities"] == {
        "can_execute": False, "can_write": False, "can_read": True,
        "handles_credentials": False, "makes_network_calls": False,
    }
    assert len(db.tables["scan_stages"]) == 1
    assert len(db.tables["findings"]) == 1
    assert db.tables["findings"][0]["id"] == str(finding.id)


@pytest.mark.parametrize(
    ("persisted_source", "persisted_target"),
    [("dashboard", "/workspace/example-server"), ("cli", "/workspace/other-server")],
)
def test_cli_upload_cannot_overwrite_an_unrelated_scan(
    monkeypatch, settings, persisted_source: str, persisted_target: str
):
    scan_id = uuid4()
    db = _UploadDb()
    db.tables["scans"].append(
        {
            "id": str(scan_id),
            "user_id": "user-1",
            "source": persisted_source,
            "target_type": "local_path",
            "target": persisted_target,
        }
    )
    request = CliUploadRequest(
        scan_id=scan_id,
        target_type="local_path",
        target="/workspace/example-server",
        risk_score=0,
        grade="A",
        status="completed",
        findings=[],
    )
    monkeypatch.setattr(cli, "enforce_rate_limit", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            cli.upload_scan(
                request,
                BackgroundTasks(),
                "user-1",
                db,  # type: ignore[arg-type]
                settings,
            )
        )

    assert exc_info.value.status_code == 409
