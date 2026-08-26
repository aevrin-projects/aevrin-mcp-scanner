"""Agent posture endpoints.

Read and delete only. There is no endpoint here that changes a configuration
on someone's machine: the dashboard cannot reach a laptop, and an API that
pretended otherwise would be a remote configuration-write service with no
device on the other end of it.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from aevrin_api.controllers import agent_controller
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import get_db, get_user_from_jwt_or_api_key
from aevrin_api.schemas.agents import (
    AgentDetailOut,
    AgentSnapshotUpload,
    AgentSnapshotUploadResponse,
    AgentSummaryOut,
    AttackPathOut,
    McpAssetOut,
    PermissionOut,
    SkillOut,
)

router = APIRouter(prefix="/agents", tags=["agents"])

# API key for `aevrin agent scan --upload`, JWT for the dashboard.
CurrentUser = Annotated[AuthenticatedUser, Depends(get_user_from_jwt_or_api_key)]
Db = Annotated[SupabaseRest, Depends(get_db)]


@router.post("/snapshots", response_model=AgentSnapshotUploadResponse)
async def upload_snapshot(
    body: AgentSnapshotUpload, user: CurrentUser, db: Db
) -> AgentSnapshotUploadResponse:
    """Record what a device found about the agents installed on it.

    Not billed as a scan. It runs no scanner, starts no container and does no
    analysis on the server; it stores a document the client already produced.
    """
    return await agent_controller.store_snapshot(body, user.id, db)


@router.get("", response_model=list[AgentSummaryOut])
async def list_agents(user: CurrentUser, db: Db) -> list[AgentSummaryOut]:
    return await agent_controller.list_agents(user.id, db)


@router.get("/mcp-servers", response_model=list[McpAssetOut])
async def list_mcp_servers(user: CurrentUser, db: Db) -> list[McpAssetOut]:
    """Every MCP server across every reported device, correlated.

    One entry per server rather than per configuration file: the same server
    reached from two agents is one asset with two installations.
    """
    return await agent_controller.list_mcp_assets(user.id, db)


@router.get("/skills", response_model=list[SkillOut])
async def list_skills(user: CurrentUser, db: Db) -> list[SkillOut]:
    """Every skill installed on every reported device."""
    return await agent_controller.list_skills(user.id, db)


@router.get("/permissions", response_model=list[PermissionOut])
async def list_permissions(user: CurrentUser, db: Db) -> list[PermissionOut]:
    """Every permission rule across every reported device, exactly as written."""
    return await agent_controller.list_permissions(user.id, db)


@router.get("/attack-paths", response_model=list[AttackPathOut])
async def list_attack_paths(user: CurrentUser, db: Db) -> list[AttackPathOut]:
    """Paths with evidence behind every step. Speculative chains are absent."""
    return await agent_controller.list_attack_paths(user.id, db)


@router.get("/{agent_id}", response_model=AgentDetailOut)
async def get_agent(agent_id: UUID, user: CurrentUser, db: Db) -> AgentDetailOut:
    return await agent_controller.get_agent(agent_id, user.id, db)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: UUID, user: CurrentUser, db: Db) -> Response:
    """Forget a device. The machine keeps its configuration; this removes
    Aevrin's copy of what was reported about it."""
    await agent_controller.delete_agent(agent_id, user.id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
