"""Account endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from aevrin_api.config import Settings, get_settings
from aevrin_api.controllers import account_controller
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import get_current_user, get_db
from aevrin_api.schemas import AccountUsageResponse

router = APIRouter(prefix="/account", tags=["account"])

CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Db = Annotated[SupabaseRest, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


@router.get("/usage", response_model=AccountUsageResponse)
async def account_usage(user: CurrentUser, db: Db, settings: Config) -> AccountUsageResponse:
    return await account_controller.account_usage(user.id, db, settings)
