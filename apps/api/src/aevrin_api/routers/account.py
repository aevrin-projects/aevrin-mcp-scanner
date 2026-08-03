from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ..config import Settings, get_settings
from ..db import SupabaseRest
from ..deps import get_current_user, get_db
from ..quota import effective_tier, get_or_create_account, get_usage
from ..schemas import AccountUsageResponse, BucketUsageOut, UsageActivityOut
from ..security import AuthenticatedUser

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/usage", response_model=AccountUsageResponse)
async def account_usage(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AccountUsageResponse:
    account = await get_or_create_account(db, user.id)
    usage = await get_usage(settings, db, user.id)
    activity_rows = await db.select(
        "scans",
        {"user_id": user.id},
        columns="id,source,target_type,target,status,score,created_at,completed_at",
        order="created_at.desc",
        limit=50,
    )
    return AccountUsageResponse(
        tier=effective_tier(account),
        paid_until=account.get("paid_until"),
        buckets=[BucketUsageOut(bucket=u.bucket, used=u.used, limit=u.limit, resets_at=u.resets_at) for u in usage],
        activity=[UsageActivityOut(**row) for row in activity_rows],
    )
