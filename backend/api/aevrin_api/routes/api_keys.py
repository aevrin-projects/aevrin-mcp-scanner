"""API key endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from aevrin_api.config import Settings, get_settings
from aevrin_api.controllers import api_key_controller
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import get_current_user, get_db
from aevrin_api.schemas import ApiKeyCreatedResponse, ApiKeyCreateRequest, ApiKeyOut

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Db = Annotated[SupabaseRest, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: ApiKeyCreateRequest, user: CurrentUser, db: Db, settings: Config
) -> ApiKeyCreatedResponse:
    return await api_key_controller.create_api_key(body, user.id, db, settings)


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(user: CurrentUser, db: Db) -> list[ApiKeyOut]:
    return await api_key_controller.list_api_keys(user.id, db)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(key_id: int, user: CurrentUser, db: Db) -> None:
    await api_key_controller.revoke_api_key(key_id, user.id, db)
