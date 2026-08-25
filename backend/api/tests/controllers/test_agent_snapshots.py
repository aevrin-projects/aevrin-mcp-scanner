"""Agent posture storage.

The security-critical assertion here is the one about credential values: the
snapshot format has no field for one, and a client that invents one must not
be able to get it into the database.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from aevrin_scanner_core.agents.models import AgentKind, ConfigScope, DiscoveredAgent
from fastapi import HTTPException

from aevrin_api.controllers import agent_controller
from aevrin_api.schemas.agents import AgentSnapshotUpload

USER = str(uuid4())


class FakeDb:
    """Records what would be written, and replays what is read."""

    def __init__(self, rows: list[dict[str, Any]] | None = None):
        self.rows = rows or []
        self.inserted: list[dict[str, Any]] = []
        self.upsert_on: str | None = None
        self.deleted: list[dict[str, str]] = []

    async def insert(self, table: str, rows: Any, *, upsert_on: str | None = None) -> list[dict]:
        self.inserted.extend(rows if isinstance(rows, list) else [rows])
        self.upsert_on = upsert_on
        return []

    async def select(self, table: str, filters: dict[str, str] | None = None, **kwargs: Any) -> list[dict]:
        rows = self.rows
        for key, value in (filters or {}).items():
            rows = [r for r in rows if str(r.get(key)) == value]
        return rows

    async def delete(self, table: str, filters: dict[str, str]) -> None:
        self.deleted.append(filters)


def snapshot(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": "1",
        "kind": "claude_code",
        "agent": {"type": "claude_code", "name": "Claude Code", "version": "1.2.3"},
        "device": {"hostname": "DEV-042", "platform": "Windows"},
        "capabilities": [{"capability": "shell", "level": "full"}],
        "mcp_servers": [
            {
                "name": "github",
                "scope": "user",
                "source_path": "/home/a/.claude.json",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
            }
        ],
        "credentials": [
            {"kind": "github_token", "present": True, "source": "environment", "location": "GITHUB_TOKEN"}
        ],
    }
    base.update(overrides)
    return base


def row(document: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    base = {
        "id": str(uuid4()),
        "user_id": USER,
        "device_id": "device-hash",
        "hostname": "DEV-042",
        "agent_type": "claude_code",
        "schema_version": "1",
        "snapshot": document or snapshot(),
        "reported_at": datetime.now(UTC).isoformat(),
    }
    base.update(overrides)
    return base


def upload(**overrides: Any) -> AgentSnapshotUpload:
    return AgentSnapshotUpload(
        device_id=overrides.pop("device_id", "device-hash"),
        agents=[DiscoveredAgent.model_validate(overrides.pop("document", snapshot()))],
    )


def test_a_credential_value_supplied_by_a_client_never_reaches_the_database():
    document = snapshot(
        credentials=[
            {
                "kind": "github_token",
                "present": True,
                "source": "environment",
                "location": "GITHUB_TOKEN",
                # No such field exists. A client inventing one must not be
                # able to smuggle a secret into storage.
                "value": "ghp_realsecrettokenvalue",
            }
        ]
    )
    db = FakeDb()
    asyncio.run(agent_controller.store_snapshot(upload(document=document), USER, db))

    stored = db.inserted[0]["snapshot"]
    assert "ghp_realsecrettokenvalue" not in str(stored)
    assert stored["credentials"][0] == {
        "kind": "github_token",
        "present": True,
        "source": "environment",
        "location": "GITHUB_TOKEN",
    }


def test_a_device_reporting_again_replaces_its_previous_row():
    db = FakeDb()
    asyncio.run(agent_controller.store_snapshot(upload(), USER, db))
    assert db.upsert_on == "user_id,device_id,agent_type"
    assert db.inserted[0]["user_id"] == USER
    assert db.inserted[0]["agent_type"] == "claude_code"


def test_a_device_without_a_machine_id_still_gets_one_stable_row():
    db = FakeDb()
    asyncio.run(agent_controller.store_snapshot(upload(device_id=None), USER, db))
    asyncio.run(agent_controller.store_snapshot(upload(device_id=None), USER, db))
    first, second = db.inserted
    assert first["device_id"] == second["device_id"]
    assert first["device_id"]  # derived from the hostname, never empty


def test_an_oversized_snapshot_is_refused():
    document = snapshot(skills=[{"name": "s" * 1000, "scope": "user", "source_path": "/x"} for _ in range(600)])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(agent_controller.store_snapshot(upload(document=document), USER, FakeDb()))
    assert exc.value.status_code == 413


def test_the_listed_summary_is_derived_from_the_stored_document():
    db = FakeDb([row()])
    agents = asyncio.run(agent_controller.list_agents(USER, db))
    assert len(agents) == 1
    listed = agents[0]
    assert listed.agent_type is AgentKind.CLAUDE_CODE
    assert listed.agent_version == "1.2.3"
    assert listed.hostname == "DEV-042"
    assert listed.mcp_server_count == 1
    # Unrestricted shell with a credential in reach: the worst combination
    # the posture rules recognise.
    assert listed.risk == "critical"
    assert listed.risk_reasons


def test_the_mcp_inventory_keeps_the_agent_and_device_each_server_came_from():
    db = FakeDb([row()])
    servers = asyncio.run(agent_controller.list_mcp_servers(USER, db))
    assert len(servers) == 1
    assert servers[0].name == "github"
    assert servers[0].scope is ConfigScope.USER
    assert servers[0].command == "npx -y @modelcontextprotocol/server-github"
    assert servers[0].hostname == "DEV-042"


def test_another_users_agent_is_not_found_rather_than_returned():
    stored = row()
    db = FakeDb([stored])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(agent_controller.get_agent(uuid4(), USER, db))
    assert exc.value.status_code == 404


def test_deleting_an_agent_forgets_only_that_row():
    stored = row()
    db = FakeDb([stored])
    asyncio.run(agent_controller.delete_agent(stored["id"], USER, db))
    assert db.deleted == [{"id": stored["id"], "user_id": USER}]
