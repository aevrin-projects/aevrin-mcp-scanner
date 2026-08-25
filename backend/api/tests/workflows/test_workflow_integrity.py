from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException

from aevrin_api.controllers import device_controller as device
from aevrin_api.controllers import hook_controller as hook
from aevrin_api.controllers.export_controller import export_report
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.schemas import DeviceTokenRequest


class _MemoryDb:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]):
        self.tables = tables

    async def select(
        self, table: str, filters: dict[str, str], **kwargs: Any
    ) -> list[dict[str, Any]]:
        return [
            row
            for row in self.tables.get(table, [])
            if all(str(row.get(key)) == value for key, value in filters.items())
        ]

    async def update(
        self, table: str, filters: dict[str, str], patch: dict[str, Any]
    ) -> list[dict[str, Any]]:
        rows = await self.select(table, filters)
        for row in rows:
            row.update(patch)
        return rows

    async def insert(
        self,
        table: str,
        rows: dict[str, Any] | list[dict[str, Any]],
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        incoming = rows if isinstance(rows, list) else [rows]
        self.tables.setdefault(table, []).extend(dict(row) for row in incoming)
        return [dict(row) for row in incoming]


def test_hook_does_not_block_on_fixed_high_finding(monkeypatch, settings) -> None:
    scan_id = str(uuid4())
    user = AuthenticatedUser("user-1", None)
    db = _MemoryDb(
        {
            "hook_cache": [
                {
                    "user_id": user.id,
                    "target": "https://github.com/a/b",
                    "last_scan_id": scan_id,
                    "last_score": 80,
                    "last_status": "completed",
                    "checked_at": datetime.now(UTC).isoformat(),
                }
            ],
            "findings": [
                {
                    "scan_id": scan_id,
                    "user_id": user.id,
                    "severity": "high",
                    "not_tested": False,
                    "triage_status": "fixed",
                }
            ],
        }
    )
    monkeypatch.setattr(hook, "enforce_rate_limit", lambda *args, **kwargs: None)

    result = asyncio.run(
        hook.check_cache(
            BackgroundTasks(),
            "https://github.com/a/b",
            "github_repo",
            user.id,
            db,  # type: ignore[arg-type]
            settings,
        )
    )

    assert result.decision == "allow_clean"
    assert result.findings_summary == []


def _blocking_finding(scan_id: str, user_id: str, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": str(uuid4()),
        "scan_id": scan_id,
        "user_id": user_id,
        "tool": "semgrep",
        "owasp_category": "MCP03",
        "severity": "critical",
        "title": "SQL injection",
        "description": "d",
        "file_path": "src/app.py",
        "line_start": 12,
        "line_end": None,
        "manifest_field": None,
        "tool_name_in_manifest": None,
        "remediation": "use parameterized queries",
        "verified": None,
        "not_tested": False,
        "triage_status": "open",
        "excluded_path": False,
        "additional_locations": [],
    }
    row.update(overrides)
    return row


def test_hook_block_returns_the_findings_that_caused_it(monkeypatch, settings) -> None:
    """A block has to carry the findings with it. The hook prints them to a
    session that has just been stopped mid-install, and a bare "blocked" with
    no file, line, or remediation leaves nobody able to act on it."""
    scan_id = str(uuid4())
    user = AuthenticatedUser("user-1", None)
    db = _MemoryDb(
        {
            "accounts": [{"user_id": user.id, "tier": "free", "paid_until": None, "signup_anchor_day": 1}],
            "hook_cache": [
                {
                    "user_id": user.id,
                    "target": "https://github.com/a/b",
                    "last_scan_id": scan_id,
                    "last_score": 40,
                    "last_status": "completed",
                    "checked_at": datetime.now(UTC).isoformat(),
                }
            ],
            "findings": [_blocking_finding(scan_id, user.id)],
        }
    )
    monkeypatch.setattr(hook, "enforce_rate_limit", lambda *args, **kwargs: None)

    result = asyncio.run(
        hook.check_cache(BackgroundTasks(), "https://github.com/a/b", "github_repo", user.id, db, settings)  # type: ignore[arg-type]
    )

    assert result.decision == "block"
    assert len(result.findings_summary) == 1
    summary = result.findings_summary[0]
    assert summary["severity"] == "critical"
    for field in ("id", "title", "owasp_category", "file_path", "line_start", "remediation"):
        assert field in summary


def test_hook_config_scan_keeps_payload_out_of_durable_targets(monkeypatch, settings) -> None:
    user = AuthenticatedUser("user-1", None)
    raw_config = '{"mcpServers":{"private":{"env":{"TOKEN":"secret"}}}}'
    db = _MemoryDb({"hook_cache": [], "scans": []})
    background_tasks = BackgroundTasks()

    async def no_quota(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(hook, "enforce_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(hook, "check_and_increment_quota", no_quota)

    result = asyncio.run(
        hook.check_cache(
            background_tasks,
            raw_config,
            "config_paste",
            user.id,
            db,  # type: ignore[arg-type]
            settings,
        )
    )

    assert result.decision == "allow_unscanned"
    assert result.target_key is not None
    assert result.target_key.startswith("Pasted MCP configuration · ")
    assert "secret" not in result.target_key
    assert db.tables["scans"][0]["target"] == result.target_key
    assert len(background_tasks.tasks) == 1


def test_device_approval_can_mint_only_one_key(monkeypatch, settings) -> None:
    device_code = "device-code"
    db = _MemoryDb(
        {
            "device_codes": [
                {
                    "device_code": device_code,
                    "status": "approved",
                    "client_kind": "cli",
                    "user_id": "user-1",
                    "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                }
            ],
            "api_keys": [],
        }
    )
    monkeypatch.setattr(device, "check_fixed_window_rate_limit", lambda *args, **kwargs: None)

    first = asyncio.run(
        device.poll_device_token(DeviceTokenRequest(device_code=device_code), db, settings)  # type: ignore[arg-type]
    )
    second = asyncio.run(
        device.poll_device_token(DeviceTokenRequest(device_code=device_code), db, settings)  # type: ignore[arg-type]
    )

    assert first.status == "approved"
    assert first.api_key is not None
    assert second.status == "expired_token"
    assert len(db.tables["api_keys"]) == 1


def test_free_tier_cannot_export_paid_report(settings) -> None:
    user = AuthenticatedUser("user-1", None)
    db = _MemoryDb(
        {
            "accounts": [
                {"user_id": user.id, "tier": "free", "paid_until": None, "signup_anchor_day": 1}
            ],
            "tier_limits": [{"tier": "free", "pdf_export": False}],
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(export_report(uuid4(), user.id, db, settings))  # type: ignore[arg-type]

    assert exc_info.value.status_code == 403
