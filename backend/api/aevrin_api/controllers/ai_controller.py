"""AI provider configuration and explanation endpoints.

The explanation endpoint has an unusual contract worth stating up front: it
returns 200 even when no explanation could be produced. An AI outage is not a
failure of the page the user is looking at -- the finding is still there, still
verified, still correct. Returning 500 would make an optional interpretation
layer look like a broken scanner, which is precisely the confusion the whole
design is meant to prevent.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.schemas.ai import (
    ExplainRequest,
    SaveProviderRequest,
    UpdateProviderRequest,
)
from aevrin_api.services.ai import credentials, evidence, explain, provider_sync
from aevrin_api.services.quota import QuotaExceeded

logger = logging.getLogger("aevrin.ai.controller")


async def list_providers(db: SupabaseRest, *, user_id: str) -> list[dict[str, Any]]:
    return await credentials.list_for_user(db, user_id=user_id)


async def save_provider(
    db: SupabaseRest, settings: Settings, *, user_id: str, body: SaveProviderRequest
) -> dict[str, Any]:
    org_id = await _org_for(db, user_id)
    try:
        return await credentials.save_credential(
            db,
            settings,
            user_id=user_id,
            org_id=org_id,
            provider=body.provider,
            api_key=body.api_key,
            model_id=body.model_id,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            system_prompt=body.system_prompt,
            priority=body.priority,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


async def update_provider(
    db: SupabaseRest, *, user_id: str, provider: str, body: UpdateProviderRequest
) -> dict[str, Any]:
    updated = await credentials.update_settings(
        db,
        user_id=user_id,
        provider=provider,
        patch=body.model_dump(exclude_unset=True),
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That provider is not configured for your account.",
        )
    return updated


async def delete_provider(db: SupabaseRest, *, user_id: str, provider: str) -> None:
    await credentials.delete_credential(db, user_id=user_id, provider=provider)


async def list_models(db: SupabaseRest, *, provider: str | None) -> list[dict[str, Any]]:
    """The models a dropdown may offer.

    Readable without a configured key, on purpose: someone choosing a provider
    should be able to see what they would get before pasting a credential.
    """
    return await provider_sync.list_catalog(db, provider=provider)


async def provider_status(db: SupabaseRest, settings: Settings) -> list[dict[str, Any]]:
    return await provider_sync.provider_status(db, settings)


async def provider_changes(db: SupabaseRest, *, limit: int = 50) -> list[dict[str, Any]]:
    return await provider_sync.recent_changes(db, limit=limit)


async def _org_for(db: SupabaseRest, user_id: str) -> str | None:
    rows = await db.select(
        "organization_members", {"user_id": user_id}, columns="org_id", limit=1
    )
    return rows[0]["org_id"] if rows else None


# --------------------------------------------------------------------------
# Explanations


async def explain_subject(
    db: SupabaseRest,
    settings: Settings,
    *,
    user_id: str,
    body: ExplainRequest,
) -> dict[str, Any]:
    """Explain one subject, or say plainly why it could not be explained."""
    try:
        document = await _gather_evidence(
            db, user_id=user_id, subject_type=body.subject_type, subject_id=body.subject_id
        )
    except PermissionError as exc:
        # The caller asked about something that is not theirs. 404 rather than
        # 403, so the response does not confirm the subject exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Nothing found to explain."
        )

    try:
        result = await explain.explain(
            db,
            settings,
            user_id=user_id,
            document=document,
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            detailed=body.detailed,
            force_refresh=body.refresh,
        )
    except explain.ExplanationUnavailable as exc:
        # 200, deliberately. See the module docstring.
        return {"available": False, "reason": str(exc)}
    except QuotaExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)
        ) from exc

    return {"available": True, **result}


async def _gather_evidence(
    db: SupabaseRest, *, user_id: str, subject_type: str, subject_id: str
) -> dict[str, Any] | None:
    """Collect the evidence for one subject, enforcing ownership as it goes.

    Ownership is checked here rather than trusted from the request, because
    this function is the thing that decides what data leaves the tenancy and
    goes to a third-party model. A subject the caller cannot read must not be
    explainable to them, or the explanation becomes an exfiltration route.
    """
    if subject_type == "finding":
        return await _finding_evidence(db, user_id=user_id, finding_id=subject_id)
    if subject_type in ("trust_grade", "listing"):
        return await _listing_evidence(db, listing_id=subject_id, subject_type=subject_type)
    if subject_type == "scan":
        return await _scan_evidence(db, user_id=user_id, scan_id=subject_id)
    return None


async def _owned_scan(db: SupabaseRest, *, user_id: str, scan_id: str) -> dict[str, Any]:
    """A scan the caller may read, or a refusal.

    Accepts a scan owned by the user directly, or one shared with them through
    their organisation -- the same rule the scans API applies, restated here
    because this path has a different consequence for getting it wrong.
    """
    rows = await db.select(
        "scans",
        {"id": scan_id},
        columns="id,user_id,org_id,score,status,unreliable_stages,target,target_type,mcp_detected",
        limit=1,
    )
    if not rows:
        raise PermissionError("Scan not found.")
    scan = rows[0]

    if str(scan.get("user_id")) == user_id:
        return scan
    org_id = scan.get("org_id")
    if org_id:
        membership = await db.select(
            "organization_members",
            {"user_id": user_id, "org_id": str(org_id)},
            columns="user_id",
            limit=1,
        )
        if membership:
            return scan
    raise PermissionError("Scan not found.")


async def _finding_evidence(
    db: SupabaseRest, *, user_id: str, finding_id: str
) -> dict[str, Any] | None:
    rows = await db.select("findings", {"id": finding_id}, limit=1)
    if not rows:
        return None
    finding = rows[0]
    scan = await _owned_scan(db, user_id=user_id, scan_id=str(finding["scan_id"]))

    return evidence.build_evidence(
        subject_type="finding",
        subject_id=finding_id,
        findings=[finding],
        coverage={
            "complete": not (scan.get("unreliable_stages") or []),
            "unreliable_stages": scan.get("unreliable_stages") or [],
        },
        context={"target_type": scan.get("target_type")},
    )


async def _scan_evidence(
    db: SupabaseRest, *, user_id: str, scan_id: str
) -> dict[str, Any] | None:
    scan = await _owned_scan(db, user_id=user_id, scan_id=scan_id)
    findings = await db.select("findings", {"scan_id": scan_id}, limit=200)
    return evidence.build_evidence(
        subject_type="scan",
        subject_id=scan_id,
        findings=findings,
        coverage={
            "complete": not (scan.get("unreliable_stages") or []),
            "unreliable_stages": scan.get("unreliable_stages") or [],
        },
        context={
            "target_type": scan.get("target_type"),
            "score": scan.get("score"),
            "mcp_detected": scan.get("mcp_detected"),
        },
    )


async def _listing_evidence(
    db: SupabaseRest, *, listing_id: str, subject_type: str
) -> dict[str, Any] | None:
    """Evidence for a public marketplace listing.

    No ownership check, because a published listing is public and its grade is
    already visible to anyone. Private listings are excluded by the filter
    below rather than by a permission error, for the same reason the detail
    endpoint 404s: confirming existence is itself a disclosure.
    """
    rows = await db.select(
        "mcp_listings",
        {"id": listing_id, "visibility": "eq.public", "status": "eq.published"},
        columns="id,slug,title,current_version,latest_version,current_trust_grade,"
        "current_security_score,current_coverage_complete,install_targets,installation,license",
        limit=1,
    )
    if not rows:
        return None
    listing = rows[0]

    version_rows = await db.select(
        "mcp_listing_versions",
        {"listing_id": listing_id, "version": f"eq.{listing.get('current_version')}"},
        columns="scan_id,code_score,mcp_score,dependency_score,trust_grade,security_score",
        limit=1,
    )
    findings: list[dict[str, Any]] = []
    if version_rows and version_rows[0].get("scan_id"):
        findings = await db.select(
            "findings", {"scan_id": str(version_rows[0]["scan_id"])}, limit=100
        )

    sub = version_rows[0] if version_rows else {}
    return evidence.build_evidence(
        subject_type=subject_type,
        subject_id=listing_id,
        findings=findings,
        trust_grade={
            "grade": listing.get("current_trust_grade"),
            "scan_score": listing.get("current_security_score"),
            "factors": [],
        },
        coverage={
            "complete": listing.get("current_coverage_complete"),
            "unreliable_stages": [],
        },
        context={
            "server": listing.get("title"),
            "scanned_version": listing.get("current_version"),
            "latest_version": listing.get("latest_version"),
            "license": listing.get("license"),
            "code_score": sub.get("code_score"),
            "mcp_score": sub.get("mcp_score"),
            "dependency_score": sub.get("dependency_score"),
        },
    )
