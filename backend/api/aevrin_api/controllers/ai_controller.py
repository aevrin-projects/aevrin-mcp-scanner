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
from uuid import UUID

from fastapi import HTTPException, status

from aevrin_api.config import Settings
from aevrin_api.controllers import agent_controller
from aevrin_api.db import SupabaseRest
from aevrin_api.schemas.ai import (
    ExplainRequest,
    SaveProviderRequest,
    UpdateProviderRequest,
)
from aevrin_api.services.ai import credentials, evidence, explain, provider_sync
from aevrin_api.services.membership import ReadScope, read_scope
from aevrin_api.services.quota import QuotaExceeded

logger = logging.getLogger("aevrin.ai.controller")


async def list_providers(db: SupabaseRest, *, user_id: str) -> list[dict[str, Any]]:
    return await credentials.list_for_user(db, user_id=user_id)


async def save_provider(
    db: SupabaseRest, settings: Settings, *, user_id: str, body: SaveProviderRequest
) -> dict[str, Any]:
    org_id = await _org_for(db, user_id)
    try:
        saved = await credentials.save_credential(
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

    # Populate the model catalogue with the key that was just saved.
    #
    # Without this the model dropdown is empty for every provider until an
    # operator sets a *_CATALOG_API_KEY, which this deployment has never had --
    # so "add a provider, then pick a model" dead-ended at the second step
    # with nothing to pick and no explanation. Aevrin's own credential is
    # still preferred when one exists (sync_provider falls back to it); this
    # only covers the case where there is none.
    #
    # Deliberately not allowed to fail the request: the credential is stored,
    # which is what the caller asked for, and sync_provider records its own
    # error state for the admin page. A vendor being briefly unreachable must
    # not look like a rejected key.
    report = await provider_sync.sync_provider(
        db, settings, body.provider, api_key=body.api_key
    )
    if not report.ok:
        logger.info(
            "model catalogue refresh after save failed for %s: %s",
            body.provider,
            report.error,
        )
    return saved


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
        UUID(body.subject_id)
    except ValueError:
        # Every subject is a row id. A malformed one is "not found", not a
        # database error surfacing as a 500.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Nothing found to explain."
        ) from None
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
    if subject_type == "scan":
        return await _scan_evidence(db, user_id=user_id, scan_id=subject_id)
    if subject_type == "agent_posture":
        return await _agent_evidence(db, user_id=user_id, agent_id=subject_id)
    return None


async def _owned_scan(db: SupabaseRest, scope: ReadScope, scan_id: str) -> dict[str, Any]:
    """A scan the caller may read, or a refusal.

    Exactly what the scans API lets the caller read (`membership.ReadScope`):
    their own scan, or one stamped with their current workspace. Findings are
    read through the same scope, so evidence never includes a row the
    finding pages would not show the caller.
    """
    rows = await scope.select(
        db,
        "scans",
        {"id": scan_id},
        columns="id,user_id,org_id,risk_score,grade,status,unreliable_stages,target,target_type,mcp_detected",
        limit=1,
    )
    if not rows:
        raise PermissionError("Scan not found.")
    return rows[0]


async def _finding_evidence(
    db: SupabaseRest, *, user_id: str, finding_id: str
) -> dict[str, Any] | None:
    scope = await read_scope(user_id, db)
    rows = await scope.select(db, "findings", {"id": finding_id}, limit=1)
    if not rows:
        return None
    finding = rows[0]
    scan = await _owned_scan(db, scope, str(finding["scan_id"]))

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


async def _agent_evidence(
    db: SupabaseRest, *, user_id: str, agent_id: str
) -> dict[str, Any] | None:
    """An agent's posture, read exactly as the agent page reads it.

    Through `agent_controller.get_agent`, not a copy of it: the same
    `ReadScope` decides who may see the snapshot (the caller's own devices and
    their workspace's, nobody else's), and the same scoring and server grades
    produce the score the explanation is about. A second read path here would
    be a second place to get tenancy wrong and a second place for the score to
    drift from the page beside it.
    """
    try:
        agent = await agent_controller.get_agent(UUID(agent_id), user_id, db)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            raise PermissionError("Agent not found.") from exc
        raise
    snapshot = agent.snapshot
    return evidence.build_evidence(
        subject_type="agent_posture",
        subject_id=agent_id,
        posture_factors=[f.model_dump() for f in agent.risk_factors],
        agent_capabilities=[
            {
                "capability": c.capability.value,
                "level": c.level.value,
                "subject": c.subject,
                "granted_by": [e.detail for e in c.evidence],
            }
            for c in snapshot.capabilities
        ],
        permission_rules=[
            {"rule": p.rule, "effect": p.effect, "scope": p.scope.value}
            for p in snapshot.permissions
        ],
        credentials_metadata=[
            {"kind": c.kind, "source": c.source, "present": c.present}
            for c in snapshot.credentials
        ],
        skills=[{"name": s.name, "description": s.description} for s in snapshot.skills],
        coverage={
            "complete": agent.coverage_complete,
            "unreliable_stages": snapshot.coverage.not_checked,
        },
        context={
            "agent": agent.agent_name,
            "posture_score": f"{agent.posture_score}/100, where 100 is the safest",
            "risk_level": agent.risk,
            "confidence": agent.confidence,
            "asks_a_person_before_acting": not snapshot.unattended,
            "permission_mode": snapshot.default_permission_mode,
            "mcp_servers": len(snapshot.mcp_servers),
            "hooks": len(snapshot.hooks),
        },
    )


async def _scan_evidence(
    db: SupabaseRest, *, user_id: str, scan_id: str
) -> dict[str, Any] | None:
    scope = await read_scope(user_id, db)
    scan = await _owned_scan(db, scope, scan_id)
    findings = await scope.select(db, "findings", {"scan_id": scan_id}, limit=200)
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
            "risk_score": scan.get("risk_score"),
            "grade": scan.get("grade"),
            "mcp_detected": scan.get("mcp_detected"),
        },
    )
