"""Backs the Claude Code PreToolUse hook (backend/hook). The hook process
itself implements the decision logic locally (never blocks synchronously on
a live scan); this endpoint just answers "what do we already know about
this target" and, on a cache miss, kicks off a background scan so the
*next* check has an answer.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from aevrin_api.config import Settings, get_settings
from aevrin_api.controllers import hook_controller
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import get_api_key_user, get_db
from aevrin_api.schemas import (
    HookCacheRequest,
    HookCacheResponse,
    HookOverrideRequest,
    HookOverrideResponse,
)

router = APIRouter(prefix="/hook", tags=["hook"])

HookUser = Annotated[AuthenticatedUser, Depends(get_api_key_user)]
Db = Annotated[SupabaseRest, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


@router.post("/override", response_model=HookOverrideResponse)
async def create_override(
    body: HookOverrideRequest, user: HookUser, db: Db, settings: Config
) -> HookOverrideResponse:
    """Backs `aevrin hook allow <target>`: the "install anyway" path. A
    person who saw the hook's block reason and decided to proceed
    shouldn't have to disable the hook entirely to do it."""
    return await hook_controller.create_override(body, user.id, db, settings)


@router.get("/cache", response_model=HookCacheResponse)
async def check_cache(
    background_tasks: BackgroundTasks,
    target: Annotated[str, Query(min_length=1, max_length=8000)],
    user: HookUser,
    db: Db,
    settings: Config,
    target_type: Literal["github_repo", "live_mcp_server", "config_paste"] = "github_repo",
) -> HookCacheResponse:
    return await hook_controller.check_cache(
        background_tasks, target, target_type, user.id, db, settings
    )


@router.post("/cache", response_model=HookCacheResponse)
async def check_cache_post(
    body: HookCacheRequest,
    background_tasks: BackgroundTasks,
    user: HookUser,
    db: Db,
    settings: Config,
) -> HookCacheResponse:
    """Body-based cache lookup used by current hooks so pasted MCP
    configuration never appears in a URL, proxy log, or durable target."""
    return await hook_controller.check_cache(
        background_tasks, body.target, body.target_type, user.id, db, settings
    )
