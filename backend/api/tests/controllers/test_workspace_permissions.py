"""Workspace permissions on shared work, asserted at the routes that act on it.

Scans, findings and agent snapshots are the workspace's shared work: a new row
is stamped with the creator's workspace (`stamp_org_id`, migration 0035). Every
API read and write of them is scoped to the caller's own user id; on top of
that, a member needs the matching permission to change them:

    scans.run        POST /scans, POST /scans/upload, POST /scans/{id}/cancel,
                     GET /cli/precheck, POST /cli/upload, POST /agents/snapshots,
                     and the hook's first scan of a target (a decision, not a 403)
    scans.delete     DELETE /scans/{id}, DELETE /scans
    findings.triage  PATCH /findings/{id} (session or X-API-Key)
    agents.delete    DELETE /agents/{id}

Every test here calls the route function, not a helper: a guard removed from a
controller must fail a test in this file. The four questions asked of each
permission: a member without it is refused and nothing changes; a member with
it succeeds; the owner succeeds whatever their role row says; someone in no
workspace is unaffected. And the workspace always comes from the caller's own
membership row, so nothing a request carries can widen what a role allows.
"""

from __future__ import annotations

import asyncio
import io
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException, UploadFile

from aevrin_api.controllers import (
    agent_controller,
    cli_controller,
    hook_controller,
    org_controller,
    scan_controller,
)
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.routes import agents as agent_routes
from aevrin_api.routes import cli as cli_routes
from aevrin_api.routes import findings as finding_routes
from aevrin_api.routes import hook as hook_routes
from aevrin_api.routes import scans as scan_routes
from aevrin_api.schemas import CliUploadRequest, CreateScanRequest, HookCacheRequest, TriageRequest
from aevrin_api.schemas.agents import AgentSnapshotUpload
from aevrin_api.services import permissions as perms
from aevrin_api.services.membership import membership_for, require_membership

ORG = str(uuid4())
OTHER_ORG = str(uuid4())

OWNER = str(uuid4())
PERMITTED = str(uuid4())  # a member whose role holds the permission under test
VIEWER = str(uuid4())  # a member whose role holds nothing
OUTSIDER = str(uuid4())  # in no workspace

OWNER_ROLE = str(uuid4())
PERMITTED_ROLE = str(uuid4())
VIEWER_ROLE = str(uuid4())


class FakeDb:
    """An in-memory PostgREST that records every write."""

    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows
        self.writes: list[tuple[str, str]] = []

    def _match(self, table: str, filters: dict[str, str] | None) -> list[dict[str, Any]]:
        rows = [r for r in self.rows if r["_table"] == table]
        for key, value in (filters or {}).items():
            if value.startswith("in."):
                wanted = value[4:-1].split(",")
                rows = [r for r in rows if str(r.get(key)) in wanted]
            else:
                rows = [r for r in rows if str(r.get(key)) == str(value)]
        return rows

    async def select(self, table: str, filters: dict[str, str] | None = None, **kwargs: Any) -> list[dict]:
        return self._match(table, filters)

    async def insert(self, table: str, rows: Any, **kwargs: Any) -> list[dict]:
        self.writes.append(("insert", table))
        made = []
        for row in rows if isinstance(rows, list) else [rows]:
            new = {"_table": table, "id": str(uuid4()),
                   "created_at": datetime.now(UTC).isoformat(), **row}
            self.rows.append(new)
            made.append(new)
        return made

    async def update(self, table: str, filters: dict[str, str], patch: dict[str, Any]) -> list[dict]:
        self.writes.append(("update", table))
        hit = self._match(table, filters)
        for row in hit:
            row.update(patch)
        return hit

    async def delete(self, table: str, filters: dict[str, str]) -> None:
        self.writes.append(("delete", table))
        for row in self._match(table, filters):
            self.rows.remove(row)


def workspace(granted: tuple[str, ...]) -> list[dict[str, Any]]:
    """ORG, owned by OWNER, with PERMITTED holding `granted` and VIEWER nothing.

    The owner's stored role row holds nothing at all, so a passing owner test
    proves the owner is served by `held_by`'s implicit catalogue, not by
    whatever their row happens to say.
    """
    return [
        {"_table": "organizations", "id": ORG, "name": "Acme", "owner_id": OWNER},
        {"_table": "organization_roles", "id": OWNER_ROLE, "org_id": ORG, "name": "Owner",
         "permissions": [], "is_owner_role": True},
        {"_table": "organization_roles", "id": PERMITTED_ROLE, "org_id": ORG, "name": "Member",
         "permissions": list(granted), "is_owner_role": False},
        {"_table": "organization_roles", "id": VIEWER_ROLE, "org_id": ORG, "name": "Viewer",
         "permissions": [], "is_owner_role": False},
        {"_table": "organization_members", "org_id": ORG, "user_id": OWNER, "role_id": OWNER_ROLE},
        {"_table": "organization_members", "org_id": ORG, "user_id": PERMITTED, "role_id": PERMITTED_ROLE},
        {"_table": "organization_members", "org_id": ORG, "user_id": VIEWER, "role_id": VIEWER_ROLE},
    ]


def org_of(user_id: str) -> str | None:
    return None if user_id == OUTSIDER else ORG


def scan_row(user_id: str, *, status: str = "completed", org_id: str | None = "auto") -> dict[str, Any]:
    return {"_table": "scans", "id": str(uuid4()), "user_id": user_id,
            "org_id": org_of(user_id) if org_id == "auto" else org_id,
            "target_type": "github_repo", "target": "https://github.com/acme/server",
            "status": status, "created_at": datetime.now(UTC).isoformat()}


def finding_row(user_id: str) -> dict[str, Any]:
    return {"_table": "findings", "id": str(uuid4()), "scan_id": str(uuid4()),
            "user_id": user_id, "org_id": org_of(user_id), "tool": "mcp-scanner",
            "owasp_category": "MCP05", "severity": "high", "title": "Fixture finding",
            "description": "Test fixture", "remediation": "Review it", "not_tested": False,
            "triage_status": "open", "created_at": datetime.now(UTC).isoformat()}


def agent_row(user_id: str) -> dict[str, Any]:
    return {"_table": "agent_snapshots", "id": str(uuid4()), "user_id": user_id,
            "org_id": org_of(user_id), "device_id": "device-1", "agent_type": "claude_code"}


def user(user_id: str) -> AuthenticatedUser:
    return AuthenticatedUser(user_id, None)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def refused(coro: Any, permission: str) -> HTTPException:
    with pytest.raises(HTTPException) as exc:
        run(coro)
    assert exc.value.status_code == 403
    # Names the permission and the label, so the person knows what to ask for.
    assert permission in str(exc.value.detail)
    assert perms.LABELS[permission] in str(exc.value.detail)
    return exc.value


@pytest.fixture
def spent(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Quota and rate limiting stubbed out, with every quota spend recorded,
    so a refusal can be shown to have cost the caller nothing."""
    calls: list[str] = []

    async def quota(settings: Any, db: Any, user_id: str, bucket: str) -> None:
        calls.append(bucket)

    async def would_exceed(*args: Any, **kwargs: Any) -> None:
        return None

    async def covered(*args: Any, **kwargs: Any) -> None:
        return None

    for module in (scan_controller, cli_controller, hook_controller):
        monkeypatch.setattr(module, "enforce_rate_limit", lambda *a, **k: None)
    for module in (scan_controller, cli_controller, hook_controller, agent_controller):
        monkeypatch.setattr(module, "check_and_increment_quota", quota)
    monkeypatch.setattr(cli_controller, "would_exceed_quota", would_exceed)
    monkeypatch.setattr(agent_controller, "_assert_device_is_covered", covered)
    return calls


def new_scan() -> CreateScanRequest:
    return CreateScanRequest(target_type="github_repo", target="https://github.com/acme/server")


def cli_result() -> CliUploadRequest:
    return CliUploadRequest(target_type="local_path", target="/work/server", status="completed",
                            risk_score=10, grade="B", mcp_tools_declared=["search"], findings=[])


def snapshot() -> AgentSnapshotUpload:
    return AgentSnapshotUpload.model_validate({
        "device_id": "device-1",
        "agents": [{"schema_version": "1", "kind": "claude_code",
                    "device": {"hostname": "DEV-1", "platform": "Linux"}}],
    })


# --- scans.run --------------------------------------------------------------


def test_a_member_without_run_scans_cannot_start_a_scan(spent: list[str], settings) -> None:
    db = FakeDb(workspace((perms.SCANS_RUN,)))
    refused(scan_routes.create_scan(new_scan(), BackgroundTasks(), user(VIEWER), db, settings),
            perms.SCANS_RUN)
    assert db.writes == []
    assert spent == []


@pytest.mark.parametrize("caller", [PERMITTED, OWNER, OUTSIDER], ids=["member-with", "owner", "outsider"])
def test_run_scans_allows_the_member_holding_it_the_owner_and_an_outsider(
    spent: list[str], settings, caller: str
) -> None:
    db = FakeDb(workspace((perms.SCANS_RUN,)))
    scan = run(scan_routes.create_scan(new_scan(), BackgroundTasks(), user(caller), db, settings))
    assert db.writes == [("insert", "scans")]
    assert str(scan.id) == db.rows[-1]["id"]
    assert spent == ["dashboard"]


def test_an_org_id_in_the_request_body_changes_nothing(spent: list[str], settings) -> None:
    """The request has no org field, and one sent anyway is dropped by the
    schema; the role comes from the membership row keyed by the caller's id."""
    db = FakeDb(workspace((perms.SCANS_RUN,)))
    body = CreateScanRequest.model_validate({
        "target_type": "github_repo", "target": "https://github.com/acme/server", "org_id": OTHER_ORG,
    })
    refused(scan_routes.create_scan(body, BackgroundTasks(), user(VIEWER), db, settings), perms.SCANS_RUN)
    assert db.writes == []


def test_a_server_side_upload_needs_run_scans(spent: list[str], settings) -> None:
    db = FakeDb(workspace((perms.SCANS_RUN,)))
    archive = UploadFile(io.BytesIO(b"not read"), filename="src.tar.gz")
    refused(scan_routes.create_scan_from_upload(BackgroundTasks(), user(VIEWER), db, settings,
                                                archive, "folder"), perms.SCANS_RUN)
    assert db.writes == []
    assert spent == []


def test_the_cli_is_refused_at_precheck_and_at_upload(spent: list[str], settings) -> None:
    db = FakeDb(workspace((perms.SCANS_RUN,)))
    refused(cli_routes.precheck(user(VIEWER), db, settings), perms.SCANS_RUN)
    refused(cli_routes.upload_scan(cli_result(), BackgroundTasks(), user(VIEWER), db, settings),
            perms.SCANS_RUN)
    assert db.writes == []
    assert spent == []


def test_a_member_with_run_scans_can_upload_a_cli_result(spent: list[str], settings) -> None:
    db = FakeDb(workspace((perms.SCANS_RUN,)))
    assert run(cli_routes.precheck(user(PERMITTED), db, settings)) == {"ok": True}
    run(cli_routes.upload_scan(cli_result(), BackgroundTasks(), user(PERMITTED), db, settings))
    assert ("insert", "scans") in db.writes
    assert spent == ["cli"]


def test_an_agent_snapshot_needs_run_scans(spent: list[str], settings) -> None:
    db = FakeDb(workspace((perms.SCANS_RUN,)))
    refused(agent_routes.upload_snapshot(snapshot(), user(VIEWER), db, settings), perms.SCANS_RUN)
    assert db.writes == []
    assert spent == []

    stored = run(agent_routes.upload_snapshot(snapshot(), user(PERMITTED), db, settings))
    assert stored.stored == 1
    assert db.writes == [("insert", "agent_snapshots")]


def test_the_hook_tells_a_viewer_the_install_was_not_checked(spent: list[str], settings) -> None:
    """A decision, not a 403: the hook fails open silently on HTTP errors, and
    a role refusal is an answer the person should see."""
    db = FakeDb(workspace((perms.SCANS_RUN,)))
    body = HookCacheRequest(target="https://github.com/acme/server")
    answer = run(hook_routes.check_cache_post(body, BackgroundTasks(), user(VIEWER), db, settings))
    assert answer.decision == "not_permitted"
    assert answer.detail is not None and perms.SCANS_RUN in answer.detail
    assert db.writes == []
    assert spent == []

    queued = run(hook_routes.check_cache_post(body, BackgroundTasks(), user(PERMITTED), db, settings))
    assert queued.decision == "allow_unscanned"
    assert db.writes == [("insert", "scans")]


def test_the_hook_still_answers_from_a_viewer_s_own_cache(spent: list[str], settings) -> None:
    """Reading a verdict already on record starts no scan, so needs nothing."""
    db = FakeDb([*workspace(()), {"_table": "hook_cache", "user_id": VIEWER,
                                  "target": "https://github.com/acme/server", "last_scan_id": None}])
    body = HookCacheRequest(target="https://github.com/acme/server")
    answer = run(hook_routes.check_cache_post(body, BackgroundTasks(), user(VIEWER), db, settings))
    assert answer.decision == "allow_clean"


def test_cancelling_a_workspace_scan_needs_run_scans(settings) -> None:
    viewer_scan = scan_row(VIEWER, status="running")
    db = FakeDb([*workspace((perms.SCANS_RUN,)), viewer_scan])
    refused(scan_routes.cancel_scan(UUID(viewer_scan["id"]), user(VIEWER), db), perms.SCANS_RUN)
    assert db.writes == []
    assert viewer_scan["status"] == "running"


# --- scans.delete -----------------------------------------------------------


def test_a_member_without_delete_scans_cannot_delete_their_workspace_scan() -> None:
    scan = scan_row(VIEWER)
    db = FakeDb([*workspace((perms.SCANS_DELETE,)), scan])
    refused(scan_routes.delete_scan(UUID(scan["id"]), user(VIEWER), db), perms.SCANS_DELETE)
    assert db.writes == []
    assert scan in db.rows


@pytest.mark.parametrize("caller", [PERMITTED, OWNER, OUTSIDER], ids=["member-with", "owner", "outsider"])
def test_delete_scans_allows_the_member_holding_it_the_owner_and_an_outsider(caller: str) -> None:
    scan = scan_row(caller)
    db = FakeDb([*workspace((perms.SCANS_DELETE,)), scan])
    response = run(scan_routes.delete_scan(UUID(scan["id"]), user(caller), db))
    assert response.status_code == 204
    assert scan not in db.rows


def test_a_role_never_reaches_a_colleague_s_scan() -> None:
    """Holding the permission does not widen row ownership: every write is
    still scoped to the caller's own user id, so a colleague's scan is 404."""
    theirs = scan_row(VIEWER)
    db = FakeDb([*workspace((perms.SCANS_DELETE,)), theirs])
    with pytest.raises(HTTPException) as exc:
        run(scan_routes.delete_scan(UUID(theirs["id"]), user(PERMITTED), db))
    assert exc.value.status_code == 404
    assert theirs in db.rows


def test_a_personal_scan_from_before_joining_is_the_member_s_own() -> None:
    """org_id null: joining by invitation does not move earlier work, so the
    workspace has no claim on it and the role is not consulted."""
    scan = scan_row(VIEWER, org_id=None)
    db = FakeDb([*workspace(()), scan])
    run(scan_routes.delete_scan(UUID(scan["id"]), user(VIEWER), db))
    assert scan not in db.rows


def test_clearing_history_is_all_or_nothing() -> None:
    personal = scan_row(VIEWER, org_id=None)
    shared = scan_row(VIEWER)
    db = FakeDb([*workspace((perms.SCANS_DELETE,)), personal, shared])
    refused(scan_routes.clear_scan_history(user(VIEWER), db), perms.SCANS_DELETE)
    assert db.writes == []
    assert personal in db.rows and shared in db.rows

    mine = scan_row(PERMITTED)
    db.rows.append(mine)
    run(scan_routes.clear_scan_history(user(PERMITTED), db))
    assert mine not in db.rows


# --- findings.triage --------------------------------------------------------


def test_a_member_without_triage_cannot_triage_their_workspace_finding() -> None:
    finding = finding_row(VIEWER)
    db = FakeDb([*workspace((perms.FINDINGS_TRIAGE,)), finding])
    body = TriageRequest(triage_status="fixed")
    refused(finding_routes.triage_finding(UUID(finding["id"]), body, user(VIEWER), db),
            perms.FINDINGS_TRIAGE)
    assert db.writes == []
    assert finding["triage_status"] == "open"


@pytest.mark.parametrize("caller", [PERMITTED, OWNER, OUTSIDER], ids=["member-with", "owner", "outsider"])
def test_triage_allows_the_member_holding_it_the_owner_and_an_outsider(caller: str) -> None:
    finding = finding_row(caller)
    db = FakeDb([*workspace((perms.FINDINGS_TRIAGE,)), finding])
    result = run(finding_routes.triage_finding(
        UUID(finding["id"]), TriageRequest(triage_status="fixed"), user(caller), db))
    assert result.triage_status == "fixed"


# --- agents.delete ----------------------------------------------------------


def test_a_member_without_remove_agents_cannot_forget_a_workspace_agent() -> None:
    agent = agent_row(VIEWER)
    db = FakeDb([*workspace((perms.AGENTS_DELETE,)), agent])
    refused(agent_routes.delete_agent(UUID(agent["id"]), user(VIEWER), db), perms.AGENTS_DELETE)
    assert db.writes == []
    assert agent in db.rows


@pytest.mark.parametrize("caller", [PERMITTED, OWNER, OUTSIDER], ids=["member-with", "owner", "outsider"])
def test_remove_agents_allows_the_member_holding_it_the_owner_and_an_outsider(caller: str) -> None:
    agent = agent_row(caller)
    db = FakeDb([*workspace((perms.AGENTS_DELETE,)), agent])
    response = run(agent_routes.delete_agent(UUID(agent["id"]), user(caller), db))
    assert response.status_code == 204
    assert agent not in db.rows


# --- the membership the guards read -----------------------------------------


def test_a_row_from_a_workspace_the_caller_left_is_governed_by_ownership() -> None:
    """A role is held only in the workspace one is in. A row still stamped
    with a workspace the caller has left is theirs by ownership, as it was
    before permissions were enforced (SECURITY.md states this edge)."""
    scan = scan_row(VIEWER, org_id=OTHER_ORG)
    db = FakeDb([*workspace(()), scan])
    run(scan_routes.delete_scan(UUID(scan["id"]), user(VIEWER), db))
    assert scan not in db.rows


def test_the_owner_role_row_is_not_what_grants_the_owner() -> None:
    membership = run(membership_for(OWNER, FakeDb(workspace(()))))
    assert membership is not None
    assert membership.role["permissions"] == []
    assert all(membership.holds(key) for key in perms.ALL_KEYS)


# --- the removed keys (ADR-051, migration 0050) ----------------------------

REMOVED = {
    "marketplace.publish", "policy.manage", "mcp.manage",
    "marketplace.submit", "ai_providers.manage", "billing.manage",
}


def test_the_migration_strips_exactly_the_keys_the_catalogue_dropped() -> None:
    from pathlib import Path

    sql = (Path(__file__).resolve().parents[4] / "backend" / "infra" / "migrations"
           / "0050_permission_catalogue.sql").read_text(encoding="utf-8")
    for key in REMOVED:
        assert f"'{key}'" in sql
        assert key not in perms.ALL_KEYS


def test_a_stored_role_still_holding_a_removed_key_stays_editable() -> None:
    """Before 0050 runs, a stored role can still carry a removed key. It is
    left out of what the API returns, so the role editor never sends it back
    to be refused as unknown, and it grants nothing."""
    from aevrin_api.schemas.orgs import RoleIn

    rows = workspace((perms.SCANS_RUN, "policy.manage", "billing.manage"))
    db = FakeDb(rows)
    owner = run(require_membership(OWNER, db))
    listed = {r.name: r for r in run(org_controller.list_roles(owner, db))}
    assert listed["Member"].permissions == [perms.SCANS_RUN]

    db.rows.append({"_table": "organization_members", "org_id": ORG, "user_id": OUTSIDER,
                    "role_id": PERMITTED_ROLE})
    member = run(require_membership(OUTSIDER, db))
    assert member.permissions == frozenset({perms.SCANS_RUN})

    saved = run(org_controller.update_role(
        UUID(PERMITTED_ROLE), RoleIn(name="Member", permissions=listed["Member"].permissions),
        owner, db))
    assert saved.permissions == [perms.SCANS_RUN]
