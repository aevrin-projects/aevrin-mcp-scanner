"""Account usage meters and identity lookups."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BucketUsageOut(BaseModel):
    bucket: str
    used: int
    limit: int | None
    resets_at: datetime


class UsageActivityOut(BaseModel):
    id: UUID
    source: str
    target_type: str
    target: str
    status: str
    score: int | None = None
    created_at: datetime
    completed_at: datetime | None = None


class MonitoredDevicesOut(BaseModel):
    """Fleet coverage, which is not a per-month meter and so is not a bucket.

    A machine is either being watched or it is not; there is nothing to reset
    at the anchor date.
    """

    used: int
    limit: int | None


class AccountUsageResponse(BaseModel):
    tier: str
    paid_until: datetime | None = None
    buckets: list[BucketUsageOut]
    monitored_devices: MonitoredDevicesOut
    activity: list[UsageActivityOut]


class AccountLookupResponse(BaseModel):
    exists: bool
    providers: list[str]
    has_password: bool
