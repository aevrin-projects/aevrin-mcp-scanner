"""Nothing in the agent surface reads across accounts.

Every one of these endpoints was added recently and each one takes a user_id;
the risk is not that the scoping is wrong today but that a later edit drops a
filter. These assert the filter is present on every read, by giving the fake
database rows belonging to somebody else and requiring that none come back.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException

from aevrin_api.controllers import agent_controller

MINE = str(uuid4())
THEIRS = str(uuid4())


class StrictDb:
    """Refuses any select that does not scope by user_id.

    A filtered-after-the-fact implementation would pass a test that only
    checked the returned rows, so the assertion is on the query itself as
    well as on the result.
    """

    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    async def select(self, table: str, filters: dict[str, str] | None = None, **kwargs: Any) -> list[dict]:
        assert filters is not None, f"unscoped select on {table}"
        assert "user_id" in filters, f"select on {table} is not scoped to a user"
        rows = [r for r in self.rows if r.get("_table") == table]
        for key, value in filters.items():
            if value.startswith("in."):
                wanted = value[4:-1].split(",")
                rows = [r for r in rows if str(r.get(key)) in wanted]
            else:
                rows = [r for r in rows if str(r.get(key)) == value]
        return rows

    async def insert(self, table: str, rows: Any, **kwargs: Any) -> list[dict]:
        return []

    async def delete(self, table: str, filters: dict[str, str]) -> None:
        assert "user_id" in filters, "delete is not scoped to a user"


def snapshot_row(user_id: str, hostname: str) -> dict[str, Any]:
    return {
        "_table": "agent_snapshots",
        "id": str(uuid4()),
        "user_id": user_id,
        "device_id": f"device-{hostname}",
        "hostname": hostname,
        "agent_type": "claude_code",
        "schema_version": "1",
        "reported_at": datetime.now(UTC).isoformat(),
        "snapshot": {
            "schema_version": "1",
            "kind": "claude_code",
            "device": {"hostname": hostname, "platform": "Linux"},
            "mcp_servers": [
                {
                    "name": "github",
                    "scope": "user",
                    "source_path": "/x",
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                }
            ],
            "skills": [{"name": "deploy", "scope": "user", "source_path": "/s"}],
            "permissions": [
                {"rule": "Bash", "effect": "allow", "scope": "user", "source_path": "/x"}
            ],
        },
    }


THEIR_ROW = snapshot_row(THEIRS, "THEIR-BOX")


@pytest.mark.parametrize(
    "call",
    [
        agent_controller.list_agents,
        agent_controller.list_mcp_assets,
        agent_controller.list_skills,
        agent_controller.list_permissions,
        agent_controller.list_attack_paths,
        agent_controller.list_policy_audit,
    ],
    ids=lambda fn: fn.__name__,
)
def test_a_listing_never_returns_another_accounts_rows(call) -> None:
    db = StrictDb([THEIR_ROW])
    assert asyncio.run(call(MINE, db)) == []


def test_a_listing_does_return_my_own_rows() -> None:
    # The negative tests above would also pass if everything returned nothing.
    db = StrictDb([snapshot_row(MINE, "MY-BOX")])
    agents = asyncio.run(agent_controller.list_agents(MINE, db))
    assert [a.hostname for a in agents] == ["MY-BOX"]


def test_fetching_another_accounts_agent_by_id_is_not_found() -> None:
    db = StrictDb([THEIR_ROW])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(agent_controller.get_agent(THEIR_ROW["id"], MINE, db))
    # Not found rather than forbidden: a 403 would confirm the id exists.
    assert exc.value.status_code == 404


def test_deleting_another_accounts_agent_is_not_found() -> None:
    db = StrictDb([THEIR_ROW])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(agent_controller.delete_agent(THEIR_ROW["id"], MINE, db))
    assert exc.value.status_code == 404


def test_policies_are_read_per_account() -> None:
    db = StrictDb([{"_table": "agent_policies", "user_id": THEIRS, "block_grade_d": True}])
    assert asyncio.run(agent_controller.get_policies(MINE, db)).block_grade_d is False
