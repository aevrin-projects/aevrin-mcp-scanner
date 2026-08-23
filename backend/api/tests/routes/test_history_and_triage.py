from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException

from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.routes.findings import triage_finding
from aevrin_api.routes.scans import clear_scan_history, delete_scan
from aevrin_api.schemas import TriageRequest


class _FakeDb:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows
        self.deleted: list[tuple[str, dict[str, str]]] = []
        self.updated: list[tuple[str, dict[str, str], dict[str, Any]]] = []

    async def select(self, table: str, filters: dict[str, str], **kwargs: Any) -> list[dict[str, Any]]:
        return [row for row in self.rows if all(str(row.get(key)) == value for key, value in filters.items())]

    async def delete(self, table: str, filters: dict[str, str]) -> None:
        self.deleted.append((table, filters))

    async def update(
        self, table: str, filters: dict[str, str], patch: dict[str, Any]
    ) -> list[dict[str, Any]]:
        self.updated.append((table, filters, patch))
        row = next(row for row in self.rows if all(str(row.get(key)) == value for key, value in filters.items()))
        row.update(patch)
        return [row]


def test_delete_scan_is_owner_scoped() -> None:
    scan_id = uuid4()
    user = AuthenticatedUser("user-1", None)
    db = _FakeDb([{"id": str(scan_id), "user_id": user.id, "status": "completed"}])

    response = asyncio.run(delete_scan(scan_id, user, db))  # type: ignore[arg-type]

    assert response.status_code == 204
    assert db.deleted == [
        ("hook_cache", {"last_scan_id": str(scan_id), "user_id": user.id}),
        ("scans", {"id": str(scan_id), "user_id": user.id}),
    ]


def test_clear_history_invalidates_hook_verdict_cache() -> None:
    user = AuthenticatedUser("user-1", None)
    db = _FakeDb([{"id": str(uuid4()), "user_id": user.id, "status": "completed"}])

    response = asyncio.run(clear_scan_history(user, db))  # type: ignore[arg-type]

    assert response.status_code == 204
    assert db.deleted == [
        ("hook_cache", {"user_id": user.id}),
        ("scans", {"user_id": user.id}),
    ]


def test_history_deletion_rejects_active_scans() -> None:
    scan_id = uuid4()
    user = AuthenticatedUser("user-1", None)
    db = _FakeDb([{"id": str(scan_id), "user_id": user.id, "status": "running"}])

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(delete_scan(scan_id, user, db))  # type: ignore[arg-type]
    assert exc_info.value.status_code == 409

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(clear_scan_history(user, db))  # type: ignore[arg-type]
    assert exc_info.value.status_code == 409
    assert db.deleted == []


def test_false_positive_persists_reason_timestamp_and_owner_filter() -> None:
    finding_id = uuid4()
    scan_id = uuid4()
    user = AuthenticatedUser("user-1", None)
    db = _FakeDb(
        [
            {
                "id": str(finding_id),
                "scan_id": str(scan_id),
                "user_id": user.id,
                "tool": "semgrep",
                "owasp_category": "MCP05",
                "severity": "medium",
                "title": "Fixture finding",
                "description": "Test fixture",
                "remediation": "Review it",
                "not_tested": False,
                "triage_status": "open",
                "created_at": datetime.now(UTC).isoformat(),
            }
        ]
    )

    result = asyncio.run(
        triage_finding(
            finding_id,
            TriageRequest(triage_status="false_positive", reason="Generated fixture"),
            user,
            db,  # type: ignore[arg-type]
        )
    )

    assert result.triage_status == "false_positive"
    assert result.triage_reason == "Generated fixture"
    table, filters, patch = db.updated[0]
    assert table == "findings"
    assert filters == {"id": str(finding_id), "user_id": user.id}
    assert patch["triaged_at"] is not None
