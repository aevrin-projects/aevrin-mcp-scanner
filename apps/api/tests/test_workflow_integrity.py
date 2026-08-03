from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException

from aevrin_api.routers import device, hook
from aevrin_api.routers.export import export_report
from aevrin_api.schemas import DeviceTokenRequest
from aevrin_api.security import AuthenticatedUser


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
            user,
            db,  # type: ignore[arg-type]
            settings,
            "github_repo",
        )
    )

    assert result.decision == "allow_clean"
    assert result.findings_summary == []


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
            user,
            db,  # type: ignore[arg-type]
            settings,
            "config_paste",
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
        asyncio.run(export_report(uuid4(), user, db, settings))  # type: ignore[arg-type]

    assert exc_info.value.status_code == 403
