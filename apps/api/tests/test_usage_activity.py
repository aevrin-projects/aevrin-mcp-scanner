from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from aevrin_api.quota import BucketUsage
from aevrin_api.routers import account
from aevrin_api.security import AuthenticatedUser


class _UsageDb:
    async def select(
        self,
        table: str,
        filters: dict[str, str],
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        assert table == "scans"
        assert filters == {"user_id": "user-1"}
        assert kwargs["order"] == "created_at.desc"
        assert kwargs["limit"] == 50
        now = datetime.now(UTC).isoformat()
        return [
            {
                "id": str(uuid4()),
                "source": "cli",
                "target_type": "github_repo",
                "target": "https://github.com/example/project",
                "status": "completed",
                "score": 91,
                "created_at": now,
                "completed_at": now,
            }
        ]


def test_usage_returns_attributed_scan_activity(monkeypatch, settings) -> None:
    now = datetime.now(UTC)

    async def fake_account(*args: Any) -> dict[str, Any]:
        return {"tier": "free", "paid_until": None}

    async def fake_usage(*args: Any) -> list[BucketUsage]:
        return [BucketUsage(bucket="cli", used=1, limit=5, resets_at=now)]

    monkeypatch.setattr(account, "get_or_create_account", fake_account)
    monkeypatch.setattr(account, "get_usage", fake_usage)

    result = asyncio.run(
        account.account_usage(
            AuthenticatedUser("user-1", None),
            _UsageDb(),  # type: ignore[arg-type]
            settings,
        )
    )

    assert len(result.activity) == 1
    assert result.activity[0].source == "cli"
    assert result.activity[0].score == 91

