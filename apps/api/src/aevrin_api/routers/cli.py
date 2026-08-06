from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from aevrin_scanner_core import (
    Finding,
    Location,
    OwaspMcpCategory,
    Severity,
    ToolName,
    compute_score,
)
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import ValidationError

from ..config import Settings, get_settings
from ..db import SupabaseRest
from ..deps import enforce_rate_limit, get_api_key_user, get_db
from ..quota import check_and_increment_quota, would_exceed_quota
from ..schemas import CliUploadFinding, CliUploadRequest, ScanOut
from ..security import AuthenticatedUser
from ..triage import triage_findings

logger = logging.getLogger("aevrin.cli_upload")

router = APIRouter(prefix="/cli", tags=["cli"])


def _to_core_finding(f: CliUploadFinding, scan_id: UUID) -> Finding:
    return Finding(
        id=f.id,
        scan_id=scan_id,
        tool=ToolName(f.tool),
        owasp_category=OwaspMcpCategory(f.owasp_category),
        severity=Severity(f.severity),
        title=f.title,
        description=f.description,
        location=Location(
            file_path=f.file_path,
            line_start=f.line_start,
            line_end=f.line_end,
            manifest_field=f.manifest_field,
            tool_name_in_manifest=f.tool_name_in_manifest,
        ),
        remediation=f.remediation,
        verified=f.verified,
        not_tested=f.not_tested,
    )


@router.get("/precheck")
async def precheck(
    user: Annotated[AuthenticatedUser, Depends(get_api_key_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, bool]:
    """The CLI calls this *before* running its local scan (which can take
    minutes) so a quota-exhausted account fails fast instead of doing real
    work first. Read-only — does not consume quota; /cli/upload is still the
    actual gate, since that's the moment a scan is genuinely recorded."""
    exceeded = await would_exceed_quota(settings, db, user.id, "cli")
    if exceeded:
        raise exceeded
    return {"ok": True}


@router.post("/upload", response_model=ScanOut, status_code=status.HTTP_201_CREATED)
async def upload_scan(
    body: CliUploadRequest,
    background: BackgroundTasks,
    user: Annotated[AuthenticatedUser, Depends(get_api_key_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ScanOut:
    """CLI already ran the full local scan (same scanner-core pipeline as
    the backend) — this just persists the result to the user's account. It
    never re-runs the pipeline server-side, so the findings list itself is
    still self-reported; the score is not, though — see below.

    We never trust the client-submitted `score` — it's recomputed here from
    the submitted findings using the same shared `compute_score` the CLI
    itself used, and that recomputed value is what gets stored. This closes
    the cheapest tampering vector (a hand-crafted upload claiming a better
    score than its own findings justify) without requiring a full
    server-side re-scan, which isn't feasible for local/private targets.
    The findings list itself remains self-reported — a fuller integrity
    story (signed local attestation, spot-check re-scans of public repo
    targets) is a documented future improvement, not something this
    upload-and-trust-the-findings model can close on its own."""
    enforce_rate_limit(settings, "cli_upload", user.id, settings.cli_uploads_per_key_per_hour)
    scan_id = body.scan_id or uuid4()

    try:
        core_findings = [_to_core_finding(f, scan_id) for f in body.findings]
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    recomputed_score = compute_score(core_findings) if body.status != "failed" else None
    if recomputed_score != body.score:
        logger.warning(
            "cli upload score mismatch for user %s target %s: client sent %s, recomputed %s",
            user.id, body.target, body.score, recomputed_score,
        )

    existing = await db.select("scans", {"id": str(scan_id)})
    if existing:
        persisted = existing[0]
        is_same_upload = (
            persisted["user_id"] == user.id
            and persisted.get("source") == "cli"
            and persisted["target_type"] == body.target_type
            and persisted["target"] == body.target
        )
        if not is_same_upload:
            # Client-generated IDs make network retries idempotent, but must
            # never let an upload overwrite a dashboard/hook scan or reuse an
            # ID for a different target.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Scan ID is already in use",
            )

    # A retry carries the same client-generated scan ID. Repair/upsert its
    # related records without consuming a second quota credit or creating a
    # duplicate history row.
    if not existing:
        await check_and_increment_quota(settings, db, user.id, "cli")

    now = datetime.now(UTC)
    scan_payload = {
        "user_id": user.id,
        "target_type": body.target_type,
        "target": body.target,
        "status": body.status,
        "source": "cli",
        "score": recomputed_score,
        "mcp_detected": body.mcp_detected,
        "unreliable_stages": body.unreliable_stages,
        "created_at": (body.created_at or now).isoformat(),
        "completed_at": (body.completed_at or now).isoformat(),
    }
    if existing:
        scan_rows = await db.update(
            "scans",
            {"id": str(scan_id), "user_id": user.id},
            scan_payload,
        )
    else:
        scan_rows = await db.insert("scans", {"id": str(scan_id), **scan_payload})

    if body.stages:
        await db.insert(
            "scan_stages",
            [
                {
                    "scan_id": str(scan_id),
                    "name": s.name,
                    "status": s.status,
                    "error": s.error,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "finished_at": s.finished_at.isoformat() if s.finished_at else None,
                }
                for s in body.stages
            ],
            upsert_on="scan_id,name",
        )
    if body.findings:
        await db.insert(
            "findings",
            [
                {
                    "id": str(f.id),
                    "scan_id": str(scan_id),
                    "user_id": user.id,
                    "tool": f.tool,
                    "owasp_category": f.owasp_category,
                    "severity": f.severity,
                    "title": f.title,
                    "description": f.description,
                    "file_path": f.file_path,
                    "line_start": f.line_start,
                    "line_end": f.line_end,
                    "manifest_field": f.manifest_field,
                    "tool_name_in_manifest": f.tool_name_in_manifest,
                    "remediation": f.remediation,
                    "verified": f.verified,
                    "not_tested": f.not_tested,
                    "raw": f.raw,
                    **({"created_at": f.created_at.isoformat()} if f.created_at else {}),
                }
                for f in body.findings
            ],
            upsert_on="id",
        )
    await db.insert(
        "hook_cache",
        {
            "user_id": user.id,
            "target": body.target,
            "last_scan_id": str(scan_id),
            "last_score": recomputed_score,
            "last_status": body.status,
            "checked_at": (body.completed_at or now).isoformat(),
        },
        upsert_on="user_id,target",
    )

    # AI review runs for CLI uploads too. Without this, a free user scanning
    # from the terminal would get a purely deterministic result while the
    # same repo scanned from the dashboard came back reviewed, which is not
    # a difference anyone would expect from the same product. Backgrounded
    # because triage takes tens of seconds and the CLI is waiting on this
    # response; it only ever adds llm_* columns after the fact, so a late or
    # failed run leaves the stored scan exactly as it is now.
    if body.findings:
        background.add_task(
            _triage_upload_best_effort, settings, db, user.id, scan_id, core_findings
        )

    return ScanOut(**scan_rows[0])


async def _triage_upload_best_effort(
    settings: Settings, db: SupabaseRest, user_id: str, scan_id: UUID, findings: list[Finding]
) -> None:
    """Swallows its own errors: this runs after the response is already sent,
    so there is nobody left to report to, and the scan it annotates is
    complete and correct without it."""
    try:
        accounts = await db.select("accounts", {"user_id": user_id})
        if not accounts:
            return
        results, note = await triage_findings(settings, accounts[0], findings)
        if note:
            await db.update("scans", {"id": str(scan_id), "user_id": user_id}, {"triage_note": note})
        triaged_at = datetime.now(UTC).isoformat()
        for result in results:
            await db.update(
                "findings",
                {"id": result.finding_id, "user_id": user_id},
                {
                    "llm_classification": result.classification,
                    "llm_severity": result.severity,
                    "llm_reasoning": result.reasoning,
                    "llm_remediation": result.remediation,
                    "llm_model": result.model,
                    "llm_triaged_at": triaged_at,
                },
            )
    except Exception:
        logger.exception("cli: background triage failed for scan %s", scan_id)
