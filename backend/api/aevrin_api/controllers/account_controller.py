"""Account overview: plan, quota buckets, and recent scan activity."""

from __future__ import annotations

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.schemas import (
    AccountUsageResponse,
    BucketUsageOut,
    MonitoredDevicesOut,
    UsageActivityOut,
)
from aevrin_api.services.quota import effective_tier, get_or_create_account, get_usage


async def account_usage(user_id: str, db: SupabaseRest, settings: Settings) -> AccountUsageResponse:
    account = await get_or_create_account(db, user_id)
    usage = await get_usage(settings, db, user_id)
    device_rows = await db.select("agent_snapshots", {"user_id": user_id}, columns="device_id")
    limit_rows = await db.select(
        "tier_limits", {"tier": effective_tier(account)}, columns="monitored_devices"
    )
    activity_rows = await db.select(
        "scans",
        {"user_id": user_id},
        columns="id,source,target_type,target,status,score,created_at,completed_at",
        order="created_at.desc",
        limit=50,
    )
    return AccountUsageResponse(
        tier=effective_tier(account),
        paid_until=account.get("paid_until"),
        buckets=[
            BucketUsageOut(bucket=u.bucket, used=u.used, limit=u.limit, resets_at=u.resets_at)
            for u in usage
        ],
        monitored_devices=MonitoredDevicesOut(
            used=len({row["device_id"] for row in device_rows}),
            limit=limit_rows[0]["monitored_devices"] if limit_rows else None,
        ),
        activity=[UsageActivityOut(**row) for row in activity_rows],
    )
