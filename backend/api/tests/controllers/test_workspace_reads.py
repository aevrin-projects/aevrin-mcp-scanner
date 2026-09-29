"""Workspace members read each other's scans, findings and agents (ADR-052).

A row is readable iff the caller created it, or it is stamped with the
caller's *current* workspace. Reading never widens changing: a colleague's row
still needs the workspace permission, and a row outside the caller's
workspace is changeable only by its creator.

Every test calls the route function, not `ReadScope`: a scope filter dropped
from one controller must fail here even though the helper still works. The
fake database also refuses any select on a shared table that is not scoped,
so a controller that reads unscoped and filters afterwards fails too.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from aevrin_api.controllers import export_controller
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.routes import agents as agent_routes
from aevrin_api.routes import ai as ai_routes
from aevrin_api.routes import export as export_routes
from aevrin_api.routes import findings as finding_routes
from aevrin_api.routes import orgs as org_routes
from aevrin_api.routes import scans as scan_routes
from aevrin_api.schemas import TriageRequest
from aevrin_api.services import permissions as perms
from aevrin_api.services.ai import explain as explain_service

ORG = str(uuid4())
OTHER_ORG = str(uuid4())

OWNER = str(uuid4())
ALICE = str(uuid4())  # member holding delete, triage and remove-agents
BOB = str(uuid4())  # member whose work Alice reads
VIEWER = str(uuid4())  # member holding nothing
STRANGER = str(uuid4())  # member of another workspace
LONER = str(uuid4())  # in no workspace
FORMER = str(uuid4())  # left ORG; their rows are still stamped with it

SHARED = {"scans", "findings", "agent_snapshots"}


class ScopedDb:
    """An in-memory PostgREST that applies `or` filters and refuses an
    unscoped read of a shared table."""

    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows
        self.writes: list[tuple[str, str, dict[str, str]]] = []
        self.rpcs: list[tuple[str, dict[str, Any]]] = []
        self.diffs: dict[str, dict[str, Any]] = {}

    def _match(self, table: str, filters: dict[str, str] | None) -> list[dict[str, Any]]:
        rows = [r for r in self.rows if r["_table"] == table]
        for key, value in (filters or {}).items():
            if value == "is.null":
                rows = [r for r in rows if r.get(key) is None]
            elif value.startswith("in."):
                wanted = value[4:-1].split(",")
                rows = [r for r in rows if str(r.get(key)) in wanted]
            else:
                rows = [r for r in rows if str(r.get(key)) == str(value)]
        return rows

    async def select(self, table: str, filters: dict[str, str] | None = None,
                     or_filter: str | None = None, **kwargs: Any) -> list[dict]:
        if table in SHARED:
            assert "user_id" in (filters or {}) or or_filter, f"unscoped select on {table}"
        rows = self._match(table, filters)
        if or_filter:
            clauses = [c.split(".eq.") for c in or_filter.strip("()").split(",")]
            assert {k for k, _ in clauses} == {"user_id", "org_id"}, or_filter
            rows = [r for r in rows if any(str(r.get(k)) == v for k, v in clauses)]
        limit = kwargs.get("limit")
        return rows[:limit] if limit else rows

    async def update(self, table: str, filters: dict[str, str], patch: dict[str, Any]) -> list[dict]:
        self.writes.append(("update", table, filters))
        hit = self._match(table, filters)
        for row in hit:
            row.update(patch)
        return hit

    async def delete(self, table: str, filters: dict[str, str]) -> None:
        self.writes.append(("delete", table, filters))
        for row in self._match(table, filters):
            self.rows.remove(row)

    async def insert(self, table: str, rows: Any, **kwargs: Any) -> list[dict]:
        raise AssertionError(f"nothing here should insert into {table}")

    async def rpc(self, fn: str, args: dict[str, Any]) -> Any:
        self.rpcs.append((fn, args))
        if fn == "org_member_emails":
            return [{"user_id": r["user_id"], "email": email_of(r["user_id"])}
                    for r in self._match("organization_members", {"org_id": args["p_org"]})]
        if fn == "scan_diff":
            return self.diffs[args["p_scan_id"]]
        raise AssertionError(f"unexpected rpc {fn}")

    def has(self, row: dict[str, Any]) -> bool:
        return any(r is row for r in self.rows)


def email_of(user_id: str) -> str:
    return f"{user_id[:8]}@example.com"


def workspaces() -> list[dict[str, Any]]:
    member_role, viewer_role, owner_role, other_role = (str(uuid4()) for _ in range(4))
    granted = [perms.SCANS_RUN, perms.SCANS_DELETE, perms.FINDINGS_TRIAGE, perms.AGENTS_DELETE]
    return [
        {"_table": "organizations", "id": ORG, "name": "Acme", "owner_id": OWNER},
        {"_table": "organizations", "id": OTHER_ORG, "name": "Other", "owner_id": STRANGER},
        {"_table": "organization_roles", "id": owner_role, "org_id": ORG, "name": "Owner",
         "permissions": [], "is_owner_role": True},
        {"_table": "organization_roles", "id": member_role, "org_id": ORG, "name": "Member",
         "permissions": granted, "is_owner_role": False},
        {"_table": "organization_roles", "id": viewer_role, "org_id": ORG, "name": "Viewer",
         "permissions": [], "is_owner_role": False},
        {"_table": "organization_roles", "id": other_role, "org_id": OTHER_ORG, "name": "Owner",
         "permissions": [], "is_owner_role": True},
        {"_table": "organization_members", "org_id": ORG, "user_id": OWNER, "role_id": owner_role},
        {"_table": "organization_members", "org_id": ORG, "user_id": ALICE, "role_id": member_role},
        {"_table": "organization_members", "org_id": ORG, "user_id": BOB, "role_id": member_role},
        {"_table": "organization_members", "org_id": ORG, "user_id": VIEWER, "role_id": viewer_role},
        {"_table": "organization_members", "org_id": OTHER_ORG, "user_id": STRANGER,
         "role_id": other_role},
        {"_table": "tier_limits", "tier": "free", "pdf_export": True},
    ]


def scan(user_id: str, org_id: str | None, *, status: str = "completed",
         target: str = "https://github.com/acme/server") -> dict[str, Any]:
    return {"_table": "scans", "id": str(uuid4()), "user_id": user_id, "org_id": org_id,
            "target_type": "github_repo", "target": target, "status": status,
            "source": "dashboard", "risk_score": 40, "grade": "C",
            "created_at": datetime.now(UTC).isoformat()}


def finding(of: dict[str, Any]) -> dict[str, Any]:
    return {"_table": "findings", "id": str(uuid4()), "scan_id": of["id"],
            "user_id": of["user_id"], "org_id": of["org_id"], "tool": "mcp-scanner",
            "owasp_category": "MCP05", "severity": "high", "title": "Fixture finding",
            "description": "Test fixture", "remediation": "Review it", "triage_status": "open",
            "created_at": datetime.now(UTC).isoformat()}


def agent(user_id: str, org_id: str | None, hostname: str) -> dict[str, Any]:
    return {
        "_table": "agent_snapshots", "id": str(uuid4()), "user_id": user_id, "org_id": org_id,
        "device_id": f"device-{hostname}", "hostname": hostname, "agent_type": "claude_code",
        "schema_version": "1", "reported_at": datetime.now(UTC).isoformat(),
        "snapshot": {
            "schema_version": "1", "kind": "claude_code",
            "device": {"hostname": hostname, "platform": "Linux"},
            "mcp_servers": [{"name": "github", "scope": "user", "source_path": "/x",
                             "transport": "stdio", "command": "npx",
                             "args": ["-y", "@modelcontextprotocol/server-github"]}],
            "skills": [{"name": "deploy", "scope": "user", "source_path": "/s"}],
            "permissions": [{"rule": "Bash", "effect": "allow", "scope": "user",
                             "source_path": "/x"}],
        },
    }


class World:
    """Bob's workspace scan, finding and agent; Bob's personal scan; a
    stranger's scan in another workspace; a former member's scan still
    stamped with ORG."""

    def __init__(self) -> None:
        self.bob_scan = scan(BOB, ORG)
        self.bob_finding = finding(self.bob_scan)
        self.bob_agent = agent(BOB, ORG, "BOB-BOX")
        self.bob_personal = scan(BOB, None, target="https://github.com/bob/private")
        self.bob_personal_finding = finding(self.bob_personal)
        self.stranger_scan = scan(STRANGER, OTHER_ORG)
        self.stranger_agent = agent(STRANGER, OTHER_ORG, "STRANGER-BOX")
        self.former_scan = scan(FORMER, ORG)
        self.db = ScopedDb([
            *workspaces(), self.bob_scan, self.bob_finding, self.bob_agent, self.bob_personal,
            self.bob_personal_finding, self.stranger_scan, self.stranger_agent, self.former_scan,
        ])


def user(user_id: str) -> AuthenticatedUser:
    return AuthenticatedUser(user_id, None)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def not_found(coro: Any) -> None:
    with pytest.raises(HTTPException) as exc:
        run(coro)
    assert exc.value.status_code == 404


def forbidden(coro: Any, permission: str) -> None:
    with pytest.raises(HTTPException) as exc:
        run(coro)
    assert exc.value.status_code == 403
    assert permission in str(exc.value.detail)


def scan_ids(user_id: str, db: ScopedDb) -> set[str]:
    return {str(s.id) for s in run(scan_routes.list_scans(user(user_id), db))}


@pytest.fixture
def exports(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Report export with the account, storage and rendering stubbed, so the
    route's own scoping is what is under test."""
    keys: list[str] = []

    async def account(db: Any, user_id: str) -> dict[str, Any]:
        return {"user_id": user_id}

    async def tier(db: Any, account: dict[str, Any]) -> str:
        return "free"

    monkeypatch.setattr(export_controller, "get_or_create_account", account)
    monkeypatch.setattr(export_controller, "entitled_tier", tier)
    monkeypatch.setattr(export_controller, "render_report_html", lambda *a: "<html></html>")
    monkeypatch.setattr(export_controller, "upload_report", lambda key, *a: keys.append(key))
    monkeypatch.setattr(export_controller, "presigned_report_url", lambda key, s: f"https://r2/{key}")
    return keys


@pytest.fixture
def explained(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_explain(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"text": "explained"}

    monkeypatch.setattr(explain_service, "explain", fake_explain)


# --- A member reads a colleague's workspace work ---------------------------


def test_a_member_lists_and_opens_a_colleague_s_scan_and_findings(settings, exports) -> None:
    w = World()
    listed = {str(s.id): s for s in run(scan_routes.list_scans(user(ALICE), w.db))}
    assert w.bob_scan["id"] in listed
    # Whose work it is, from the same emails GET /orgs/members shows.
    assert listed[w.bob_scan["id"]].mine is False
    assert listed[w.bob_scan["id"]].created_by == email_of(BOB)

    scan_id = UUID(w.bob_scan["id"])
    opened = run(scan_routes.get_scan(scan_id, user(ALICE), w.db))
    assert opened.risk_summary is not None and opened.created_by == email_of(BOB)
    run(scan_routes.get_scan_stages(scan_id, user(ALICE), w.db))
    assert [str(f.id) for f in run(scan_routes.get_scan_findings(scan_id, user(ALICE), w.db))] == [
        w.bob_finding["id"]
    ]
    assert str(run(finding_routes.get_finding(UUID(w.bob_finding["id"]), user(ALICE), w.db)).id) == (
        w.bob_finding["id"]
    )
    run(export_routes.export_report(scan_id, user(ALICE), w.db, settings))
    # Stored under the exporting caller, not under the colleague who ran it.
    assert exports == [f"reports/{ALICE}/{scan_id}.html"]


def test_the_creator_sees_their_own_scan_as_theirs() -> None:
    w = World()
    mine = {str(s.id): s for s in run(scan_routes.list_scans(user(BOB), w.db))}
    assert mine[w.bob_scan["id"]].mine is True and mine[w.bob_scan["id"]].created_by is None
    # Their personal scan is in their own list.
    assert w.bob_personal["id"] in mine


def test_a_member_reads_every_agent_view_of_a_colleague_s_agent() -> None:
    w = World()
    alice = user(ALICE)
    agents = run(agent_routes.list_agents(alice, w.db))
    assert [a.hostname for a in agents] == ["BOB-BOX"]
    assert agents[0].mine is False and agents[0].created_by == email_of(BOB)

    detail = run(agent_routes.get_agent(UUID(w.bob_agent["id"]), alice, w.db))
    assert detail.hostname == "BOB-BOX" and detail.created_by == email_of(BOB)
    assert {i.hostname for a in run(agent_routes.list_mcp_servers(alice, w.db))
            for i in a.installations} == {"BOB-BOX"}
    assert {s.hostname for s in run(agent_routes.list_skills(alice, w.db))} == {"BOB-BOX"}
    assert {p.hostname for p in run(agent_routes.list_permissions(alice, w.db))} == {"BOB-BOX"}
    assert {p.hostname for p in run(agent_routes.list_attack_paths(alice, w.db))} <= {"BOB-BOX"}


def test_ai_explain_reads_exactly_what_the_scan_page_reads(explained, settings) -> None:
    w = World()
    body = {"subject_type": "scan", "subject_id": w.bob_scan["id"]}
    assert run(ai_routes.explain(body, w.db, settings, user(ALICE)))["available"] is True
    not_found(ai_routes.explain(body, w.db, settings, user(STRANGER)))
    personal = {"subject_type": "scan", "subject_id": w.bob_personal["id"]}
    not_found(ai_routes.explain(personal, w.db, settings, user(ALICE)))


# --- Everyone else reads nothing -------------------------------------------


@pytest.mark.parametrize("outsider", [STRANGER, LONER], ids=["other-workspace", "no-workspace"])
def test_a_non_member_neither_lists_nor_opens_workspace_work(outsider: str, settings, exports) -> None:
    w = World()
    caller = user(outsider)
    assert w.bob_scan["id"] not in scan_ids(outsider, w.db)
    assert "BOB-BOX" not in {a.hostname for a in run(agent_routes.list_agents(caller, w.db))}
    for view in (agent_routes.list_mcp_servers, agent_routes.list_skills,
                 agent_routes.list_permissions, agent_routes.list_attack_paths):
        assert all(item.model_dump().get("hostname") != "BOB-BOX" for item in run(view(caller, w.db)))

    scan_id = UUID(w.bob_scan["id"])
    not_found(scan_routes.get_scan(scan_id, caller, w.db))
    not_found(scan_routes.get_scan_stages(scan_id, caller, w.db))
    not_found(scan_routes.scan_diff(scan_id, caller, w.db))
    not_found(export_routes.export_report(scan_id, caller, w.db, settings))
    assert run(scan_routes.get_scan_findings(scan_id, caller, w.db)) == []
    not_found(finding_routes.get_finding(UUID(w.bob_finding["id"]), caller, w.db))
    not_found(agent_routes.get_agent(UUID(w.bob_agent["id"]), caller, w.db))
    assert exports == []
    # And no member identity reaches them.
    assert all(args.get("p_org") != ORG for _, args in w.db.rpcs)


def test_the_other_workspace_is_invisible_to_this_one() -> None:
    w = World()
    assert w.stranger_scan["id"] not in scan_ids(ALICE, w.db)
    not_found(scan_routes.get_scan(UUID(w.stranger_scan["id"]), user(ALICE), w.db))
    not_found(agent_routes.get_agent(UUID(w.stranger_agent["id"]), user(ALICE), w.db))


def test_a_personal_scan_stays_with_its_creator() -> None:
    """org_id null: work from before joining by invitation is not shared."""
    w = World()
    assert w.bob_personal["id"] not in scan_ids(ALICE, w.db)
    not_found(scan_routes.get_scan(UUID(w.bob_personal["id"]), user(ALICE), w.db))
    not_found(finding_routes.get_finding(UUID(w.bob_personal_finding["id"]), user(ALICE), w.db))
    assert run(scan_routes.get_scan_findings(UUID(w.bob_personal["id"]), user(ALICE), w.db)) == []
    assert w.bob_personal["id"] in scan_ids(BOB, w.db)


def test_a_former_member_keeps_their_own_work_and_loses_their_colleagues() -> None:
    w = World()
    # FORMER has no membership row: they left.
    assert scan_ids(FORMER, w.db) == {w.former_scan["id"]}
    not_found(scan_routes.get_scan(UUID(w.bob_scan["id"]), user(FORMER), w.db))

    # Their work stays with the team, credited to nobody still in it.
    shared = {str(s.id): s for s in run(scan_routes.list_scans(user(ALICE), w.db))}
    assert shared[w.former_scan["id"]].mine is False
    assert shared[w.former_scan["id"]].created_by is None


def test_leaving_ends_access_to_colleagues_work_immediately() -> None:
    w = World()
    assert w.bob_scan["id"] in scan_ids(ALICE, w.db)
    run(org_routes.leave_organization(user(ALICE), w.db))
    assert w.bob_scan["id"] not in scan_ids(ALICE, w.db)
    not_found(scan_routes.get_scan(UUID(w.bob_scan["id"]), user(ALICE), w.db))
    not_found(agent_routes.get_agent(UUID(w.bob_agent["id"]), user(ALICE), w.db))


# --- Reading never widens changing -----------------------------------------


def test_a_viewer_reads_a_colleague_s_work_but_cannot_change_it() -> None:
    w = World()
    viewer = user(VIEWER)
    run(scan_routes.get_scan(UUID(w.bob_scan["id"]), viewer, w.db))
    run(finding_routes.get_finding(UUID(w.bob_finding["id"]), viewer, w.db))
    run(agent_routes.get_agent(UUID(w.bob_agent["id"]), viewer, w.db))

    forbidden(scan_routes.delete_scan(UUID(w.bob_scan["id"]), viewer, w.db), perms.SCANS_DELETE)
    forbidden(finding_routes.triage_finding(UUID(w.bob_finding["id"]),
                                            TriageRequest(triage_status="fixed"), viewer, w.db),
              perms.FINDINGS_TRIAGE)
    forbidden(agent_routes.delete_agent(UUID(w.bob_agent["id"]), viewer, w.db), perms.AGENTS_DELETE)
    assert w.db.writes == []
    assert w.db.has(w.bob_scan) and w.db.has(w.bob_agent)
    assert w.bob_finding["triage_status"] == "open"


def test_a_member_holding_the_permissions_changes_a_colleague_s_work() -> None:
    w = World()
    alice = user(ALICE)
    triaged = run(finding_routes.triage_finding(
        UUID(w.bob_finding["id"]), TriageRequest(triage_status="fixed"), alice, w.db))
    assert triaged.triage_status == "fixed"
    run(agent_routes.delete_agent(UUID(w.bob_agent["id"]), alice, w.db))
    run(scan_routes.delete_scan(UUID(w.bob_scan["id"]), alice, w.db))
    assert not w.db.has(w.bob_agent) and not w.db.has(w.bob_scan)
    # Every write is keyed on the row's creator, so it touches only the row
    # that was authorised, and the creator's own hook verdict for that scan.
    assert ("delete", "hook_cache", {"last_scan_id": w.bob_scan["id"], "user_id": BOB}) in w.db.writes
    assert all(filters.get("user_id") == BOB for _, _, filters in w.db.writes)


def test_nobody_changes_a_row_outside_their_workspace() -> None:
    """Holding every permission does not reach a personal row or another
    workspace: those are not readable, so 404 and nothing written."""
    w = World()
    not_found(scan_routes.delete_scan(UUID(w.bob_personal["id"]), user(OWNER), w.db))
    not_found(finding_routes.triage_finding(UUID(w.bob_personal_finding["id"]),
                                            TriageRequest(triage_status="fixed"), user(OWNER), w.db))
    not_found(agent_routes.delete_agent(UUID(w.stranger_agent["id"]), user(OWNER), w.db))
    assert w.db.writes == []


def test_only_the_creator_cancels_a_running_scan() -> None:
    w = World()
    running = scan(BOB, ORG, status="running")
    w.db.rows.append(running)
    not_found(scan_routes.cancel_scan(UUID(running["id"]), user(OWNER), w.db))
    assert running["status"] == "running"


def test_a_former_member_s_row_is_now_changeable_by_the_team() -> None:
    """ADR-051 left it deletable by nobody but its creator; it is a workspace
    row, so a member with the permission can remove it."""
    w = World()
    run(scan_routes.delete_scan(UUID(w.former_scan["id"]), user(ALICE), w.db))
    assert not w.db.has(w.former_scan)


def test_clearing_history_deletes_only_the_caller_s_own_scans() -> None:
    w = World()
    mine = scan(ALICE, ORG)
    w.db.rows.append(mine)
    run(scan_routes.clear_scan_history(user(ALICE), w.db))
    assert not w.db.has(mine)
    assert w.db.has(w.bob_scan) and w.db.has(w.former_scan)
    assert all(filters == {"user_id": ALICE} for _, _, filters in w.db.writes)


# --- The diff never shows a scan the caller cannot open --------------------


def test_a_colleague_s_diff_against_their_personal_scan_is_withheld() -> None:
    w = World()
    w.db.diffs[w.bob_scan["id"]] = {
        "previous_scan_id": w.bob_personal["id"],
        "resolved": [{"title": "Private finding", "file_path": "secret.py", "tool": "x"}],
        "introduced": [], "unchanged_count": 0,
    }
    diff = run(scan_routes.scan_diff(UUID(w.bob_scan["id"]), user(ALICE), w.db))
    assert diff == {"previous_scan_id": None, "resolved": [], "introduced": [], "unchanged_count": 0}
    # Asked as the scan's creator, whose own previous scan it is.
    assert ("scan_diff", {"p_scan_id": w.bob_scan["id"], "p_user_id": BOB}) in w.db.rpcs
    # Bob can open his personal scan, so he gets the diff.
    assert run(scan_routes.scan_diff(UUID(w.bob_scan["id"]), user(BOB), w.db))["resolved"]


def test_a_colleague_s_diff_against_a_workspace_scan_is_shown() -> None:
    w = World()
    earlier = scan(BOB, ORG)
    w.db.rows.append(earlier)
    w.db.diffs[w.bob_scan["id"]] = {"previous_scan_id": earlier["id"], "resolved": [],
                                    "introduced": [{"title": "New"}], "unchanged_count": 1}
    diff = run(scan_routes.scan_diff(UUID(w.bob_scan["id"]), user(ALICE), w.db))
    assert diff["previous_scan_id"] == earlier["id"]
