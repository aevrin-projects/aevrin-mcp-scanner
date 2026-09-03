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

from aevrin_api.config import Settings
from aevrin_api.controllers import agent_controller
from aevrin_api.schemas.agents import AgentSnapshotUpload

USER = str(uuid4())


class _FakeRedis:
    """Counters in memory. Without this the quota check reaches for the real
    Upstash URL in the test settings and every store test pays a timeout."""

    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    def expire(self, key: str, seconds: int) -> None:
        return None

    def get(self, key: str) -> int | None:
        return self.values.get(key)


@pytest.fixture(autouse=True)
def _patch_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    fake = _FakeRedis()
    monkeypatch.setattr("aevrin_api.integrations.redis_client.get_redis", lambda settings=None: fake)
    monkeypatch.setattr(
        "aevrin_api.integrations.redis_client.get_fallback_redis", lambda settings=None: None
    )
    return fake


class FakeDb:
    """Records what would be written, and replays what is read."""

    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        *,
        scans: list[dict[str, Any]] | None = None,
        findings: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ):
        self.rows = rows or []
        self.tables = {
            "scans": scans or [],
            "findings": findings or [],
            "accounts": [
                {"user_id": USER, "tier": "free", "paid_until": None, "signup_anchor_day": 1}
            ],
            # Unlimited by default: the tests that care about a limit set one.
            "tier_limits": [
                {
                    "tier": "free",
                    "agent_scans_per_month": None,
                    "monitored_devices": kwargs.pop("monitored_devices", None),
                }
            ],
        }
        self.inserted: list[dict[str, Any]] = []
        self.upsert_on: str | None = None
        self.deleted: list[dict[str, str]] = []

    async def insert(self, table: str, rows: Any, *, upsert_on: str | None = None) -> list[dict]:
        self.inserted.extend(rows if isinstance(rows, list) else [rows])
        self.upsert_on = upsert_on
        return []

    async def select(self, table: str, filters: dict[str, str] | None = None, **kwargs: Any) -> list[dict]:
        # Tables the store path touches but these tests do not model return
        # empty, which every caller already reads as "nothing configured".
        rows = self.rows if table == "agent_snapshots" else self.tables.get(table, [])
        for key, value in (filters or {}).items():
            if value.startswith("in."):
                wanted = value[4:-1].split(",")
                rows = [r for r in rows if str(r.get(key)) in wanted]
            else:
                rows = [r for r in rows if str(r.get(key)) == value]
        # Honoured because the controller relies on it: "the newest scan of a
        # target wins" is only true if the query really came back newest first.
        order = kwargs.get("order")
        if order:
            column, _, direction = order.partition(".")
            rows = sorted(rows, key=lambda r: str(r.get(column) or ""), reverse=direction == "desc")
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


SETTINGS = Settings(
    supabase_url="https://test.supabase.co",
    supabase_anon_key="anon-key",
    supabase_service_role_key="service-role-key",
    api_key_pepper="test-pepper",
    upstash_redis_rest_url="https://test-redis.upstash.io",
    upstash_redis_rest_token="redis-token",
    r2_account_id="account-id",
    r2_access_key_id="access-key",
    r2_secret_access_key="secret-key",
    r2_s3_endpoint="https://account-id.r2.cloudflarestorage.com",
    web_origin="http://localhost:3000",
)


def store(upload_body: AgentSnapshotUpload, db: Any):
    return asyncio.run(agent_controller.store_snapshot(upload_body, USER, db, SETTINGS))


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
    store(upload(document=document), db)

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
    store(upload(), db)
    assert db.upsert_on == "user_id,device_id,agent_type"
    assert db.inserted[0]["user_id"] == USER
    assert db.inserted[0]["agent_type"] == "claude_code"


def test_a_device_without_a_machine_id_still_gets_one_stable_row():
    db = FakeDb()
    store(upload(device_id=None), db)
    store(upload(device_id=None), db)
    first, second = db.inserted
    assert first["device_id"] == second["device_id"]
    assert first["device_id"]  # derived from the hostname, never empty


def test_an_oversized_snapshot_is_refused():
    document = snapshot(skills=[{"name": "s" * 1000, "scope": "user", "source_path": "/x"} for _ in range(600)])
    with pytest.raises(HTTPException) as exc:
        store(upload(document=document), FakeDb())
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
    assert listed.posture_score < 100
    assert listed.confidence
    assert [f.reason for f in listed.risk_factors]


def test_the_mcp_inventory_keeps_the_agent_and_device_each_server_came_from():
    db = FakeDb([row()])
    assets = asyncio.run(agent_controller.list_mcp_assets(USER, db))
    assert len(assets) == 1
    asset = assets[0]
    assert asset.name == "github"
    assert asset.installation_count == 1
    installation = asset.installations[0]
    assert installation.scope is ConfigScope.USER
    assert installation.command == "npx -y @modelcontextprotocol/server-github"
    assert installation.hostname == "DEV-042"


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


def http_server_snapshot() -> dict[str, Any]:
    return snapshot(
        mcp_servers=[
            {
                "name": "context7",
                "scope": "user",
                "source_path": "/home/a/.claude.json",
                "transport": "http",
                "url": "https://mcp.context7.com/mcp",
            }
        ]
    )


def scan_row(
    scan_id: str,
    target: str,
    *,
    status: str = "completed",
    score: int = 100,
    mcp_capabilities: dict[str, bool] | None = None,
) -> dict[str, Any]:
    return {
        "id": scan_id,
        "user_id": USER,
        "target": target,
        "target_type": "live_mcp_server",
        "status": status,
        "score": score,
        "mcp_capabilities": mcp_capabilities,
        "created_at": datetime.now(UTC).isoformat(),
    }


def finding_row(scan_id: str, severity: str) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "scan_id": scan_id,
        "user_id": USER,
        "tool": "semgrep",
        "owasp_category": "MCP01",
        "severity": severity,
        "title": "Example",
        "description": "Example",
        "remediation": "Fix it",
        "triage_status": "open",
    }


def test_a_stdio_server_is_reported_unscanned_rather_than_assumed_clean():
    # There is no target for Aevrin to have scanned. A grade here would be a
    # claim about evidence that does not exist.
    db = FakeDb([row()], scans=[scan_row(str(uuid4()), "https://example.com/mcp")])
    assets = asyncio.run(agent_controller.list_mcp_assets(USER, db))
    assert assets[0].transport == "stdio"
    assert assets[0].trust is None


def test_a_scanned_http_server_carries_the_grade_from_its_own_scan():
    scan_id = str(uuid4())
    db = FakeDb(
        [row(http_server_snapshot())],
        scans=[scan_row(scan_id, "https://mcp.context7.com/mcp", score=72)],
        findings=[finding_row(scan_id, "high"), finding_row(scan_id, "medium")],
    )
    trust = asyncio.run(agent_controller.list_mcp_assets(USER, db))[0].trust
    assert trust is not None
    assert str(trust.scan_id) == scan_id
    assert trust.scan_score == 72
    assert trust.grade in {"B", "C", "D"}
    # The letter arrives with the factors that produced it, or it is an
    # opinion with better typography.
    assert any("high-severity" in factor.reason for factor in trust.factors)


def test_live_capability_data_reaches_the_agent_posture_grade():
    """scan.mcp_capabilities for a live_mcp_server scan comes from
    remote_mcp.py's own handshake, not discover_tools() - before this was
    wired up, _trust_by_identity never read the column at all, so a live
    server's real, established capability evidence never reached its own
    grade here (ADR-022)."""
    scan_id = str(uuid4())
    db = FakeDb(
        [row(http_server_snapshot())],
        scans=[scan_row(
            scan_id, "https://mcp.context7.com/mcp", score=100,
            mcp_capabilities={"can_execute": True, "can_write": False, "can_read": True,
                              "handles_credentials": False, "makes_network_calls": False},
        )],
    )
    trust = asyncio.run(agent_controller.list_mcp_assets(USER, db))[0].trust
    assert trust is not None
    assert any("command-execution" in factor.reason for factor in trust.factors)


def test_an_http_server_that_was_never_scanned_has_no_grade():
    db = FakeDb([row(http_server_snapshot())], scans=[scan_row(str(uuid4()), "https://elsewhere/mcp")])
    assert asyncio.run(agent_controller.list_mcp_assets(USER, db))[0].trust is None


def test_an_incomplete_scan_cannot_produce_the_top_grade():
    scan_id = str(uuid4())
    db = FakeDb(
        [row(http_server_snapshot())],
        scans=[scan_row(scan_id, "https://mcp.context7.com/mcp", status="incomplete", score=100)],
    )
    trust = asyncio.run(agent_controller.list_mcp_assets(USER, db))[0].trust
    assert trust is not None
    assert trust.grade != "A"
    assert any("incomplete" in factor.reason for factor in trust.factors)


def test_the_newest_scan_of_a_target_wins():
    older, newer = str(uuid4()), str(uuid4())
    scans = [
        scan_row(newer, "https://mcp.context7.com/mcp"),
        scan_row(older, "https://mcp.context7.com/mcp"),
    ]
    # Listed oldest-first, so passing depends on the ordering, not the order
    # they happen to be written here.
    scans[0]["created_at"] = "2026-08-26T10:00:00+00:00"
    scans[1]["created_at"] = "2026-08-20T10:00:00+00:00"
    scans.reverse()
    db = FakeDb([row(http_server_snapshot())], scans=scans)
    trust = asyncio.run(agent_controller.list_mcp_assets(USER, db))[0].trust
    assert trust is not None
    assert str(trust.scan_id) == newer


def project_server_snapshot(hostname: str = "DEV-042") -> dict[str, Any]:
    """The same GitHub server, configured in a project rather than globally."""
    document = snapshot(
        mcp_servers=[
            {
                "name": "gh",  # a different local name for the same server
                "scope": "project",
                "source_path": "/repo/acme/.mcp.json",
                "transport": "stdio",
                "command": "npx",
                "args": ["@modelcontextprotocol/server-github"],
            }
        ]
    )
    document["project_root"] = "/repo/acme"
    document["device"] = {"hostname": hostname, "platform": "Linux"}
    return document


def test_the_same_server_from_two_agents_is_one_asset_with_two_installations():
    db = FakeDb(
        [
            row(),  # Claude Code, global, npx -y @modelcontextprotocol/server-github
            row(project_server_snapshot("DEV-099"), device_id="other", hostname="DEV-099"),
        ]
    )
    assets = asyncio.run(agent_controller.list_mcp_assets(USER, db))
    assert len(assets) == 1
    asset = assets[0]
    assert asset.identity_kind == "npm"
    assert asset.identity_confidence == "high"
    assert asset.installation_count == 2
    assert asset.device_count == 2
    assert asset.agent_count == 2


def test_global_and_project_scope_are_both_kept_on_the_one_asset():
    db = FakeDb([row(), row(project_server_snapshot(), device_id="other")])
    asset = asyncio.run(agent_controller.list_mcp_assets(USER, db))[0]
    assert [s.value for s in asset.scopes] == ["project", "user"]
    assert asset.project_count == 1
    assert {i.project_root for i in asset.installations} == {None, "/repo/acme"}


def test_two_different_servers_are_never_merged():
    other = snapshot(
        mcp_servers=[
            {
                "name": "postgres",
                "scope": "user",
                "source_path": "/home/b/.claude.json",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-postgres"],
            }
        ]
    )
    db = FakeDb([row(), row(other, device_id="other")])
    assets = asyncio.run(agent_controller.list_mcp_assets(USER, db))
    assert len(assets) == 2
    assert {a.identity_key for a in assets} == {
        "npm:@modelcontextprotocol/server-github",
        "npm:@modelcontextprotocol/server-postgres",
    }


def test_a_server_known_only_by_name_is_marked_uncertain_rather_than_merged():
    def named(name: str) -> dict[str, Any]:
        return snapshot(
            mcp_servers=[
                {"name": name, "scope": "user", "source_path": "/x", "transport": "unknown"}
            ]
        )

    db = FakeDb([row(named("thing")), row(named("other"), device_id="d2")])
    assets = asyncio.run(agent_controller.list_mcp_assets(USER, db))
    assert len(assets) == 2
    assert {a.identity_confidence for a in assets} == {"low"}


def test_a_server_disabled_in_one_place_is_not_enabled_everywhere():
    disabled = snapshot(
        mcp_servers=[
            {
                "name": "github",
                "scope": "user",
                "source_path": "/home/b/.codex/config.toml",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "enabled": False,
            }
        ]
    )
    db = FakeDb([row(), row(disabled, device_id="other")])
    asset = asyncio.run(agent_controller.list_mcp_assets(USER, db))[0]
    assert asset.installation_count == 2
    assert asset.enabled_everywhere is False


def test_a_scan_correlates_through_identity_not_the_raw_string():
    # A trailing slash is not a different server.
    scan_id = str(uuid4())
    db = FakeDb(
        [row(http_server_snapshot())],
        scans=[scan_row(scan_id, "https://mcp.context7.com/mcp/")],
    )
    trust = asyncio.run(agent_controller.list_mcp_assets(USER, db))[0].trust
    assert trust is not None
    assert str(trust.scan_id) == scan_id


def test_skills_carry_the_agent_and_device_they_are_installed_on():
    document = snapshot(
        skills=[
            {"name": "deploy", "scope": "user", "source_path": "/home/a/.claude/skills/deploy/SKILL.md",
             "description": "Ships things"}
        ]
    )
    skills = asyncio.run(agent_controller.list_skills(USER, FakeDb([row(document)])))
    assert len(skills) == 1
    assert skills[0].name == "deploy"
    assert skills[0].hostname == "DEV-042"
    assert skills[0].description == "Ships things"


def test_permission_rules_are_listed_allow_first():
    document = snapshot(
        permissions=[
            {"rule": "Read(**)", "effect": "deny", "scope": "user", "source_path": "/x"},
            {"rule": "Bash(npm run *)", "effect": "allow", "scope": "user", "source_path": "/x"},
            {"rule": "WebFetch", "effect": "ask", "scope": "user", "source_path": "/x"},
        ]
    )
    rules = asyncio.run(agent_controller.list_permissions(USER, FakeDb([row(document)])))
    # A rule that grants is what someone scanning this page needs to see.
    assert [r.effect for r in rules] == ["allow", "ask", "deny"]
    assert rules[0].hostname == "DEV-042"


def test_an_agent_with_no_skills_or_rules_contributes_nothing():
    db = FakeDb([row()])
    assert asyncio.run(agent_controller.list_skills(USER, db)) == []
    assert asyncio.run(agent_controller.list_permissions(USER, db)) == []


def test_attack_paths_carry_their_agent_and_device():
    document = snapshot(
        capabilities=[
            {
                "capability": "shell",
                "level": "full",
                "evidence": [
                    {"detail": "permissions.allow: Bash", "source_path": "/home/a/.claude/settings.json"}
                ],
            }
        ],
        credentials=[
            {
                "kind": "aws_credentials_file",
                "present": True,
                "source": "file",
                "location": "/home/a/.aws/credentials",
            }
        ],
    )
    paths = asyncio.run(agent_controller.list_attack_paths(USER, FakeDb([row(document)])))
    assert len(paths) == 1
    assert paths[0].severity == "critical"
    assert paths[0].hostname == "DEV-042"
    assert [step.label for step in paths[0].steps] == ["Shell", "aws", "aws credentials file"]
    assert paths[0].steps[0].evidence == ["permissions.allow: Bash"]


def test_a_machine_with_no_evidenced_path_reports_none():
    # The default fixture has unrestricted shell but no mapped credential.
    document = snapshot(
        capabilities=[{"capability": "shell", "level": "full"}],
        credentials=[
            {"kind": "claude_code_credentials", "present": True, "source": "file", "location": "/x"}
        ],
    )
    assert asyncio.run(agent_controller.list_attack_paths(USER, FakeDb([row(document)]))) == []


def test_one_upload_is_one_posture_scan_however_many_agents_it_carries(_patch_redis):
    # Claude Code and Codex found by the same command are one
    # `aevrin agent scan`, and billing two would charge for the tool being
    # thorough.
    codex = snapshot(kind="codex", agent={"type": "codex", "name": "Codex"})
    body = AgentSnapshotUpload(
        device_id="device-hash",
        agents=[
            DiscoveredAgent.model_validate(snapshot()),
            DiscoveredAgent.model_validate(codex),
        ],
    )
    db = FakeDb()
    result = store(body, db)
    assert result.stored == 2
    assert sum(_patch_redis.values.values()) == 1


def test_a_new_device_beyond_the_plan_allowance_is_refused_as_not_monitored():
    db = FakeDb([row(device_id="already-here")], monitored_devices=1)
    with pytest.raises(HTTPException) as exc:
        store(upload(device_id="a-second-machine"), db)
    assert exc.value.status_code == 402
    # A limit is a gap in coverage, never a clean result.
    assert "not monitored" in str(exc.value.detail)
    assert "not the same as it being low risk" in str(exc.value.detail)


def test_a_device_already_being_tracked_keeps_reporting_at_the_limit():
    # A plan change must never silently stop watching a machine that was
    # already being watched.
    db = FakeDb([row(device_id="already-here")], monitored_devices=1)
    assert store(upload(device_id="already-here"), db).stored == 1


def test_an_unlimited_plan_admits_any_device():
    db = FakeDb([row(device_id="a"), row(device_id="b")])
    assert store(upload(device_id="c"), db).stored == 1
