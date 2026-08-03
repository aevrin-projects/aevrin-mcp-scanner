from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..db import SupabaseRest
from ..deps import get_current_user, get_db, get_user_from_jwt_or_api_key
from ..schemas import FindingOut, TriageRequest
from ..security import AuthenticatedUser

router = APIRouter(prefix="/findings", tags=["findings"])


@router.get("/{finding_id}", response_model=FindingOut)
async def get_finding(
    finding_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
) -> FindingOut:
    rows = await db.select("findings", {"id": str(finding_id), "user_id": user.id})
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    return FindingOut(**rows[0])


@router.patch("/{finding_id}", response_model=FindingOut)
async def triage_finding(
    finding_id: UUID,
    body: TriageRequest,
    # Both the dashboard (JWT) and `aevrin findings triage` (API key) call
    # this — that's the CLI-side "false report" action.
    user: Annotated[AuthenticatedUser, Depends(get_user_from_jwt_or_api_key)],
    db: Annotated[SupabaseRest, Depends(get_db)],
) -> FindingOut:
    existing = await db.select("findings", {"id": str(finding_id), "user_id": user.id})
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    audit_patch: dict[str, str | None]
    if body.triage_status == "open":
        audit_patch = {"triage_reason": None, "triaged_at": None}
    else:
        audit_patch = {
            "triage_reason": body.reason,
            "triaged_at": datetime.now(UTC).isoformat(),
        }
    rows = await db.update(
        "findings",
        {"id": str(finding_id), "user_id": user.id},
        {"triage_status": body.triage_status, **audit_patch},
    )
    return FindingOut(**rows[0])
