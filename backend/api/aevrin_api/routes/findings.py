"""Finding endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from aevrin_api.controllers import finding_controller
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import get_current_user, get_db, get_user_from_jwt_or_api_key
from aevrin_api.schemas import FindingOut, TriageRequest

router = APIRouter(prefix="/findings", tags=["findings"])

Db = Annotated[SupabaseRest, Depends(get_db)]


@router.get("/{finding_id}", response_model=FindingOut)
async def get_finding(
    finding_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Db,
) -> FindingOut:
    return await finding_controller.get_finding(finding_id, user.id, db)


@router.patch("/{finding_id}", response_model=FindingOut)
async def triage_finding(
    finding_id: UUID,
    body: TriageRequest,
    # Both the dashboard (JWT) and `aevrin findings triage` (API key) call
    # this; that's the CLI-side "false report" action.
    user: Annotated[AuthenticatedUser, Depends(get_user_from_jwt_or_api_key)],
    db: Db,
) -> FindingOut:
    return await finding_controller.triage_finding(finding_id, body, user.id, db)
