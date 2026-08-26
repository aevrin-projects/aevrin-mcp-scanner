"""Agent posture: store the snapshot a device reported, and read it back.

The snapshot is stored as one document. Everything the dashboard lists --
agents, MCP servers, skills, risk -- is derived from it here, so there is one
definition of each of those and it lives next to the model rather than in
whichever page happened to need it first.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from aevrin_scanner_core import Finding
from aevrin_scanner_core.agents.attack_paths import find_attack_paths
from aevrin_scanner_core.agents.grade import grade_mcp_server
from aevrin_scanner_core.agents.identity import mcp_identity
from aevrin_scanner_core.agents.models import ConfigScope, DiscoveredAgent, McpServerRef
from aevrin_scanner_core.agents.posture import assess_posture
from fastapi import HTTPException, status

from aevrin_api.db import SupabaseRest
from aevrin_api.schemas.agents import (
    AgentDetailOut,
    AgentSnapshotUpload,
    AgentSnapshotUploadResponse,
    AgentSummaryOut,
    AttackPathOut,
    AttackStepOut,
    GradeFactorOut,
    McpAssetOut,
    McpInstallationOut,
    McpTrustOut,
    PermissionOut,
    PostureFactorOut,
    SkillOut,
)

# A posture snapshot is configuration metadata: a few hundred kilobytes is
# already a machine with an unusual number of skills. The cap is here so a
# malformed or hostile client cannot push arbitrary volume into a jsonb column.
MAX_SNAPSHOT_BYTES = 512 * 1024

# How far back to look for a scan of a configured server. Bounded so the
# inventory stays one query regardless of how much history an account has.
GRADE_SCAN_LOOKBACK = 200


def _device_id(upload: AgentSnapshotUpload, agent: DiscoveredAgent) -> str:
    if upload.device_id:
        return upload.device_id
    hostname = agent.device.hostname if agent.device else "unknown"
    return hashlib.sha256(f"hostname:{hostname}".encode()).hexdigest()


async def store_snapshot(
    upload: AgentSnapshotUpload, user_id: str, db: SupabaseRest
) -> AgentSnapshotUploadResponse:
    now = datetime.now(UTC).isoformat()
    rows = []
    for agent in upload.agents:
        document = agent.model_dump(mode="json")
        size = len(json.dumps(document))
        if size > MAX_SNAPSHOT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Snapshot for {agent.kind.value} is {size} bytes; the limit is {MAX_SNAPSHOT_BYTES}.",
            )
        rows.append(
            {
                "user_id": user_id,
                "device_id": _device_id(upload, agent),
                "hostname": agent.device.hostname if agent.device else "unknown",
                "agent_type": agent.kind.value,
                "schema_version": agent.schema_version,
                "snapshot": document,
                "reported_at": now,
            }
        )

    # A device reporting again replaces its previous answer: the snapshot
    # describes what is true on that machine now, not what it has ever been.
    await db.insert("agent_snapshots", rows, upsert_on="user_id,device_id,agent_type")
    return AgentSnapshotUploadResponse(stored=len(rows))


def _summary(row: dict[str, Any], mcp_grades: dict[str, str] | None = None) -> AgentSummaryOut:
    agent = DiscoveredAgent.model_validate(row["snapshot"])
    posture = assess_posture(agent, mcp_grades=mcp_grades)
    return AgentSummaryOut(
        id=UUID(row["id"]),
        agent_type=agent.kind,
        agent_name=agent.agent.name if agent.agent else agent.kind.value,
        agent_version=agent.agent.version if agent.agent else None,
        device_id=row["device_id"],
        hostname=row["hostname"],
        platform=agent.device.platform if agent.device else None,
        reported_at=row["reported_at"],
        posture_score=posture.score,
        risk=posture.risk.value,
        confidence=posture.confidence.value,
        risk_factors=[
            PostureFactorOut(points=f.points, reason=f.reason) for f in posture.factors
        ],
        mcp_server_count=len(agent.mcp_servers),
        skill_count=len(agent.skills),
        plugin_count=len(agent.plugins),
        hook_count=len(agent.hooks),
        coverage_complete=agent.coverage.complete and not agent.unreadable_paths,
    )


async def _grades_for_agents(
    rows: list[dict[str, Any]], user_id: str, db: SupabaseRest
) -> dict[str, dict[str, str]]:
    """Per snapshot row, the trust grade of each server it configures.

    Only grades a scan actually produced. An unscanned server is absent
    rather than present-and-good, which is what keeps the posture engine from
    crediting an agent for evidence nobody gathered.
    """
    servers: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        agent = DiscoveredAgent.model_validate(row["snapshot"])
        servers[row["id"]] = [(s.name, mcp_identity(s).key) for s in agent.mcp_servers]

    trust = await _trust_by_identity({key for pairs in servers.values() for _, key in pairs}, user_id, db)
    return {
        row_id: {name: trust[key].grade for name, key in pairs if key in trust}
        for row_id, pairs in servers.items()
    }


async def list_agents(user_id: str, db: SupabaseRest) -> list[AgentSummaryOut]:
    rows = await db.select("agent_snapshots", {"user_id": user_id}, order="reported_at.desc")
    grades = await _grades_for_agents(rows, user_id, db)
    return [_summary(row, grades.get(row["id"])) for row in rows]


async def get_agent(agent_id: UUID, user_id: str, db: SupabaseRest) -> AgentDetailOut:
    rows = await db.select(
        "agent_snapshots", {"id": str(agent_id), "user_id": user_id}, limit=1
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
    grades = await _grades_for_agents(rows, user_id, db)
    summary = _summary(rows[0], grades.get(rows[0]["id"]))
    return AgentDetailOut(
        **summary.model_dump(), snapshot=DiscoveredAgent.model_validate(rows[0]["snapshot"])
    )


def _scan_identity_key(target: str) -> str:
    """The identity of a scanned target, in the same vocabulary configured
    servers use, so the two can be matched at all."""
    return mcp_identity(
        McpServerRef(
            name=target, scope=ConfigScope.USER, source_path="", transport="http", url=target
        )
    ).key


async def _trust_by_identity(
    wanted: set[str], user_id: str, db: SupabaseRest
) -> dict[str, McpTrustOut]:
    """Grade each configured server that has actually been scanned.

    Matched on identity rather than on the raw string, so a scan of
    `https://x/mcp/` correlates with a config of `https://x/mcp`. Nothing
    looser: guessing at a match would attach one server's evidence to
    another, which is worse than showing nothing.

    stdio servers never match. They are a command on someone's machine, there
    is no target for Aevrin to have scanned, and they are reported as
    unscanned rather than assumed clean.
    """
    if not wanted:
        return {}

    scans = await db.select(
        "scans",
        {"user_id": user_id, "target_type": "live_mcp_server"},
        columns="id,target,score,status,created_at",
        order="created_at.desc",
        limit=GRADE_SCAN_LOOKBACK,
    )
    latest: dict[str, dict[str, Any]] = {}
    for scan in scans:
        if scan["status"] not in ("completed", "incomplete"):
            continue
        key = _scan_identity_key(scan["target"])
        if key in wanted and key not in latest:
            latest[key] = scan
    if not latest:
        return {}

    ids = ",".join(scan["id"] for scan in latest.values())
    rows = await db.select("findings", {"scan_id": f"in.({ids})", "user_id": user_id})
    findings_by_scan: dict[str, list[Finding]] = {}
    for row in rows:
        findings_by_scan.setdefault(row["scan_id"], []).append(Finding.model_validate(row))

    trust: dict[str, McpTrustOut] = {}
    for key, scan in latest.items():
        result = grade_mcp_server(
            findings=findings_by_scan.get(scan["id"], []),
            scan_score=scan["score"],
            # A scan that did not finish cannot support the top of the scale,
            # the same rule the CLI applies to the same grade.
            coverage_complete=scan["status"] != "incomplete",
            transport=scan["target"],
        )
        trust[key] = McpTrustOut(
            scan_id=UUID(scan["id"]),
            scanned_at=scan["created_at"],
            scan_score=result.scan_score,
            grade=result.grade.value,
            label=result.label,
            recommended_action=result.recommended_action,
            factors=[GradeFactorOut(points=f.points, reason=f.reason) for f in result.factors],
        )
    return trust


async def list_mcp_assets(user_id: str, db: SupabaseRest) -> list[McpAssetOut]:
    """Every MCP server across every reported device, correlated.

    One entry per server, not per configuration file: the same server reached
    from two agents is one asset with two installations. Grouping happens here
    rather than in the page, so the CLI, the API and the dashboard can never
    disagree about what counts as one server.
    """
    rows = await db.select("agent_snapshots", {"user_id": user_id}, order="reported_at.desc")
    grouped: dict[str, list[McpInstallationOut]] = {}
    identities: dict[str, Any] = {}

    for row in rows:
        agent = DiscoveredAgent.model_validate(row["snapshot"])
        for server in agent.mcp_servers:
            identity = mcp_identity(server)
            identities.setdefault(identity.key, identity)
            grouped.setdefault(identity.key, []).append(
                McpInstallationOut(
                    agent_id=UUID(row["id"]),
                    agent_type=agent.kind,
                    agent_name=agent.agent.name if agent.agent else agent.kind.value,
                    device_id=row["device_id"],
                    hostname=row["hostname"],
                    name=server.name,
                    scope=server.scope,
                    project_root=agent.project_root,
                    source_path=server.source_path,
                    transport=server.transport,
                    command=" ".join([server.command, *server.args]) if server.command else None,
                    url=server.url,
                    enabled=server.enabled,
                    auto_approved=server.auto_approved,
                    reported_at=row["reported_at"],
                )
            )

    trust = await _trust_by_identity(set(grouped), user_id, db)

    assets: list[McpAssetOut] = []
    for key, installations in grouped.items():
        identity = identities[key]
        first = installations[0]
        assets.append(
            McpAssetOut(
                identity_key=key,
                identity_kind=identity.kind,
                identity_label=identity.label,
                identity_confidence=identity.confidence.value,
                # The most common local name. People name the same server
                # differently, and the majority reading is the least
                # surprising label to put on one row.
                name=Counter(i.name for i in installations).most_common(1)[0][0],
                transport=first.transport,
                url=next((i.url for i in installations if i.url), None),
                command=next((i.command for i in installations if i.command), None),
                installation_count=len(installations),
                device_count=len({i.device_id for i in installations}),
                agent_count=len({i.agent_id for i in installations}),
                project_count=len({i.project_root for i in installations if i.project_root}),
                scopes=sorted({i.scope for i in installations}, key=lambda s: s.value),
                # False when it is switched off anywhere: "you are running
                # this" and "you are running this in one of three places" are
                # different answers.
                enabled_everywhere=all(i.enabled for i in installations),
                installations=installations,
                trust=trust.get(key),
            )
        )
    assets.sort(key=lambda a: (a.name.lower(), a.identity_key))
    return assets


async def list_skills(user_id: str, db: SupabaseRest) -> list[SkillOut]:
    rows = await db.select("agent_snapshots", {"user_id": user_id}, order="reported_at.desc")
    skills: list[SkillOut] = []
    for row in rows:
        agent = DiscoveredAgent.model_validate(row["snapshot"])
        skills.extend(
            SkillOut(
                name=skill.name,
                description=skill.description,
                scope=skill.scope,
                source_path=skill.source_path,
                agent_id=UUID(row["id"]),
                agent_type=agent.kind,
                hostname=row["hostname"],
            )
            for skill in agent.skills
        )
    skills.sort(key=lambda s: (s.name.lower(), s.hostname))
    return skills


async def list_permissions(user_id: str, db: SupabaseRest) -> list[PermissionOut]:
    rows = await db.select("agent_snapshots", {"user_id": user_id}, order="reported_at.desc")
    permissions: list[PermissionOut] = []
    for row in rows:
        agent = DiscoveredAgent.model_validate(row["snapshot"])
        permissions.extend(
            PermissionOut(
                rule=permission.rule,
                effect=permission.effect,
                scope=permission.scope,
                source_path=permission.source_path,
                agent_id=UUID(row["id"]),
                agent_type=agent.kind,
                hostname=row["hostname"],
            )
            for permission in agent.permissions
        )
    # Allow first: a rule that grants is what someone scanning this page needs
    # to see, and a deny buried above it wastes the top of the screen.
    order = {"allow": 0, "ask": 1, "deny": 2}
    permissions.sort(key=lambda p: (order.get(p.effect, 3), p.rule.lower(), p.hostname))
    return permissions


async def list_attack_paths(user_id: str, db: SupabaseRest) -> list[AttackPathOut]:
    """Every evidenced path across every reported device, worst first."""
    rows = await db.select("agent_snapshots", {"user_id": user_id}, order="reported_at.desc")
    grades = await _grades_for_agents(rows, user_id, db)

    found: list[AttackPathOut] = []
    for row in rows:
        agent = DiscoveredAgent.model_validate(row["snapshot"])
        for path in find_attack_paths(agent, mcp_grades=grades.get(row["id"], {})):
            found.append(
                AttackPathOut(
                    key=path.key,
                    title=path.title,
                    source=path.source,
                    target=path.target,
                    severity=path.severity.value,
                    confidence=path.confidence.value,
                    steps=[
                        AttackStepOut(
                            label=step.label,
                            detail=step.detail,
                            evidence=[e.detail for e in step.evidence],
                        )
                        for step in path.steps
                    ],
                    remediation=path.remediation,
                    agent_id=UUID(row["id"]),
                    agent_type=agent.kind,
                    hostname=row["hostname"],
                )
            )
    order = {"critical": 0, "high": 1, "medium": 2}
    found.sort(key=lambda p: (order.get(p.severity, 3), p.hostname, p.key))
    return found


async def delete_agent(agent_id: UUID, user_id: str, db: SupabaseRest) -> None:
    rows = await db.select("agent_snapshots", {"id": str(agent_id), "user_id": user_id}, limit=1)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
    await db.delete("agent_snapshots", {"id": str(agent_id), "user_id": user_id})
