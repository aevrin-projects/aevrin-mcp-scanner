"""Reading one finding and recording a triage decision on it."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status

from aevrin_api.db import SupabaseRest
from aevrin_api.schemas import FindingOut, TriageRequest
from aevrin_api.services import membership
from aevrin_api.services import permissions as perms

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")


async def get_finding(finding_id: UUID, user_id: str, db: SupabaseRest) -> FindingOut:
    """The caller's own finding, or one stamped with their workspace."""
    scope = await membership.read_scope(user_id, db)
    rows = await scope.select(db, "findings", {"id": str(finding_id)})
    if not rows:
        raise _NOT_FOUND
    return FindingOut(**rows[0])


async def triage_finding(
    finding_id: UUID, body: TriageRequest, user_id: str, db: SupabaseRest
) -> FindingOut:
    scope = await membership.read_scope(user_id, db)
    existing = await scope.select(db, "findings", {"id": str(finding_id)})
    if not existing:
        raise _NOT_FOUND
    # One check for both callers of this route: the dashboard (JWT) and the
    # CLI's `aevrin findings triage` (API key), which resolve to the same
    # user id before they get here. Readable is not changeable: a finding in
    # the caller's workspace needs `findings.triage` whoever it belongs to.
    scope.require_change(existing[0], perms.FINDINGS_TRIAGE)
    # Reopening clears the audit trail rather than leaving a stale reason
    # attached to a finding that is once again open.
    audit_patch: dict[str, str | None]
    if body.triage_status == "open":
        audit_patch = {"triage_reason": None, "triaged_at": None}
    else:
        audit_patch = {"triage_reason": body.reason, "triaged_at": datetime.now(UTC).isoformat()}
    # Keyed on the row's creator: the write touches exactly the row that was
    # authorised above.
    rows = await db.update(
        "findings",
        {"id": str(finding_id), "user_id": str(existing[0]["user_id"])},
        {"triage_status": body.triage_status, **audit_patch},
    )
    return FindingOut(**rows[0])
