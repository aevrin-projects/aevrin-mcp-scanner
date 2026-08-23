"""Report export endpoint."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from aevrin_api.config import Settings, get_settings
from aevrin_api.controllers import export_controller
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import get_current_user, get_db

router = APIRouter(prefix="/scans", tags=["export"])

CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Db = Annotated[SupabaseRest, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


@router.get("/{scan_id}/export")
async def export_report(
    scan_id: UUID, user: CurrentUser, db: Db, settings: Config
) -> dict[str, str]:
    return await export_controller.export_report(scan_id, user.id, db, settings)
