"""Agent posture: store the snapshot a device reported, and read it back.

The snapshot is stored as one document. Everything the dashboard lists --
agents, MCP servers, skills, risk -- is derived from it here, so there is one
definition of each of those and it lives next to the model rather than in
whichever page happened to need it first.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from aevrin_scanner_core import Finding
from aevrin_scanner_core.agents.grade import grade_mcp_server
from aevrin_scanner_core.agents.models import DiscoveredAgent
from aevrin_scanner_core.agents.posture import assess_posture
from fastapi import HTTPException, status

from aevrin_api.db import SupabaseRest
from aevrin_api.schemas.agents import (
    AgentDetailOut,
    AgentSnapshotUpload,
    AgentSnapshotUploadResponse,
    AgentSummaryOut,
    GradeFactorOut,
    McpServerInventoryOut,
    McpTrustOut,
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


def _summary(row: dict[str, Any]) -> AgentSummaryOut:
    agent = DiscoveredAgent.model_validate(row["snapshot"])
    posture = assess_posture(agent)
    return AgentSummaryOut(
        id=UUID(row["id"]),
        agent_type=agent.kind,
        agent_name=agent.agent.name if agent.agent else agent.kind.value,
        agent_version=agent.agent.version if agent.agent else None,
        device_id=row["device_id"],
        hostname=row["hostname"],
        platform=agent.device.platform if agent.device else None,
        reported_at=row["reported_at"],
        risk=posture.risk.value,
        risk_reasons=posture.reasons,
        mcp_server_count=len(agent.mcp_servers),
        skill_count=len(agent.skills),
        plugin_count=len(agent.plugins),
        hook_count=len(agent.hooks),
        coverage_complete=agent.coverage.complete and not agent.unreadable_paths,
    )


async def list_agents(user_id: str, db: SupabaseRest) -> list[AgentSummaryOut]:
    rows = await db.select("agent_snapshots", {"user_id": user_id}, order="reported_at.desc")
    return [_summary(row) for row in rows]


async def get_agent(agent_id: UUID, user_id: str, db: SupabaseRest) -> AgentDetailOut:
    rows = await db.select(
        "agent_snapshots", {"id": str(agent_id), "user_id": user_id}, limit=1
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
    summary = _summary(rows[0])
    return AgentDetailOut(
        **summary.model_dump(), snapshot=DiscoveredAgent.model_validate(rows[0]["snapshot"])
    )


async def _trust_by_target(targets: set[str], user_id: str, db: SupabaseRest) -> dict[str, McpTrustOut]:
    """Grade each configured server that has actually been scanned.

    Matched on the exact scanned target. A configured server and a scan are
    only the same thing when the URL is the same string; guessing at a looser
    match would attach one server's evidence to another, which is worse than
    showing nothing.

    stdio servers never match. They are a command on someone's machine, there
    is no target for Aevrin to have scanned, and they are reported as
    unscanned rather than assumed clean.
    """
    if not targets:
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
        target = scan["target"]
        if target in targets and target not in latest and scan["status"] in ("completed", "incomplete"):
            latest[target] = scan
    if not latest:
        return {}

    ids = ",".join(scan["id"] for scan in latest.values())
    rows = await db.select("findings", {"scan_id": f"in.({ids})", "user_id": user_id})
    findings_by_scan: dict[str, list[Finding]] = {}
    for row in rows:
        findings_by_scan.setdefault(row["scan_id"], []).append(Finding.model_validate(row))

    trust: dict[str, McpTrustOut] = {}
    for target, scan in latest.items():
        result = grade_mcp_server(
            findings=findings_by_scan.get(scan["id"], []),
            scan_score=scan["score"],
            # A scan that did not finish cannot support the top of the scale,
            # the same rule the CLI applies to the same grade.
            coverage_complete=scan["status"] != "incomplete",
            transport=target,
        )
        trust[target] = McpTrustOut(
            scan_id=UUID(scan["id"]),
            scanned_at=scan["created_at"],
            scan_score=result.scan_score,
            grade=result.grade.value,
            label=result.label,
            recommended_action=result.recommended_action,
            factors=[GradeFactorOut(points=f.points, reason=f.reason) for f in result.factors],
        )
    return trust


async def list_mcp_servers(user_id: str, db: SupabaseRest) -> list[McpServerInventoryOut]:
    rows = await db.select("agent_snapshots", {"user_id": user_id}, order="reported_at.desc")
    inventory: list[McpServerInventoryOut] = []
    agents = [(row, DiscoveredAgent.model_validate(row["snapshot"])) for row in rows]
    trust = await _trust_by_target(
        {server.url for _, agent in agents for server in agent.mcp_servers if server.url}, user_id, db
    )
    for row, agent in agents:
        for server in agent.mcp_servers:
            inventory.append(
                McpServerInventoryOut(
                    name=server.name,
                    scope=server.scope,
                    transport=server.transport,
                    command=" ".join([server.command, *server.args]) if server.command else None,
                    url=server.url,
                    auto_approved=server.auto_approved,
                    source_path=server.source_path,
                    project_root=agent.project_root,
                    agent_id=UUID(row["id"]),
                    agent_type=agent.kind,
                    agent_name=agent.agent.name if agent.agent else agent.kind.value,
                    hostname=row["hostname"],
                    reported_at=row["reported_at"],
                    trust=trust.get(server.url) if server.url else None,
                )
            )
    inventory.sort(key=lambda s: (s.name.lower(), s.hostname))
    return inventory


async def delete_agent(agent_id: UUID, user_id: str, db: SupabaseRest) -> None:
    rows = await db.select("agent_snapshots", {"id": str(agent_id), "user_id": user_id}, limit=1)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
    await db.delete("agent_snapshots", {"id": str(agent_id), "user_id": user_id})
