"""Regression coverage: /cli/upload must never trust the client-submitted
score — it's recomputed server-side from the submitted findings using the
same shared compute_score the CLI itself used, closing the cheapest
tampering vector (a hand-crafted upload claiming a better score than its
own findings justify)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from aevrin_scanner_core import compute_score
from fastapi import HTTPException

from aevrin_api.routers import cli
from aevrin_api.routers.cli import _to_core_finding
from aevrin_api.schemas import CliUploadFinding, CliUploadRequest, CliUploadStage
from aevrin_api.security import AuthenticatedUser


def _finding(severity: str) -> CliUploadFinding:
    return CliUploadFinding(
        id=uuid4(),
        tool="bandit",
        owasp_category="MCP05",
        severity=severity,
        title="Example finding",
        description="Example description",
        remediation="Fix it",
    )


def test_recomputed_score_ignores_a_falsely_low_client_score():
    scan_id = uuid4()
    findings = [_finding("info")]  # info findings never affect score
    recomputed = compute_score([_to_core_finding(f, scan_id) for f in findings])
    claimed_by_client = 0  # a malicious/broken client claiming "critical, do not use"
    assert recomputed == 100
    assert recomputed != claimed_by_client


def test_recomputed_score_ignores_a_falsely_high_client_score():
    scan_id = uuid4()
    findings = [_finding("critical")]
    recomputed = compute_score([_to_core_finding(f, scan_id) for f in findings])
    claimed_by_client = 100  # a malicious client hiding a real critical finding's impact
    assert recomputed < 100
    assert recomputed != claimed_by_client


def test_to_core_finding_round_trips_location_fields():
    scan_id = uuid4()
    f = CliUploadFinding(
        id=uuid4(),
        tool="semgrep",
        owasp_category="MCP01",
        severity="high",
        title="t",
        description="d",
        file_path="app.py",
        line_start=10,
        line_end=12,
        remediation="r",
    )
    core = _to_core_finding(f, scan_id)
    assert core.scan_id == scan_id
    assert core.location.file_path == "app.py"
    assert core.location.line_start == 10
    assert core.location.line_end == 12


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
        score=60,
        status="completed",
        created_at=started,
        completed_at=completed,
        mcp_detected=True,
        stages=[
            CliUploadStage(
                name="static_analysis",
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

    first = asyncio.run(cli.upload_scan(request, user, db, settings))  # type: ignore[arg-type]
    second = asyncio.run(cli.upload_scan(request, user, db, settings))  # type: ignore[arg-type]

    assert first.id == second.id == scan_id
    assert quota_calls == 1
    assert len(db.tables["scans"]) == 1
    assert db.tables["scans"][0]["source"] == "cli"
    assert db.tables["scans"][0]["created_at"] == started.isoformat()
    assert db.tables["scans"][0]["completed_at"] == completed.isoformat()
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
        score=100,
        status="completed",
        findings=[],
    )
    monkeypatch.setattr(cli, "enforce_rate_limit", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            cli.upload_scan(
                request,
                AuthenticatedUser("user-1", "developer@example.com"),
                db,  # type: ignore[arg-type]
                settings,
            )
        )

    assert exc_info.value.status_code == 409
