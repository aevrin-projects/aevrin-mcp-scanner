"""Reading one finding and recording a triage decision on it."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status

from aevrin_api.db import SupabaseRest
from aevrin_api.schemas import FindingOut, TriageRequest

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")


async def get_finding(finding_id: UUID, user_id: str, db: SupabaseRest) -> FindingOut:
    rows = await db.select("findings", {"id": str(finding_id), "user_id": user_id})
    if not rows:
        raise _NOT_FOUND
    return FindingOut(**rows[0])


async def triage_finding(
    finding_id: UUID, body: TriageRequest, user_id: str, db: SupabaseRest
) -> FindingOut:
    existing = await db.select("findings", {"id": str(finding_id), "user_id": user_id})
    if not existing:
        raise _NOT_FOUND
    # Reopening clears the audit trail rather than leaving a stale reason
    # attached to a finding that is once again open.
    audit_patch: dict[str, str | None]
    if body.triage_status == "open":
        audit_patch = {"triage_reason": None, "triaged_at": None}
    else:
        audit_patch = {"triage_reason": body.reason, "triaged_at": datetime.now(UTC).isoformat()}
    rows = await db.update(
        "findings",
        {"id": str(finding_id), "user_id": user_id},
        {"triage_status": body.triage_status, **audit_patch},
    )
    return FindingOut(**rows[0])
