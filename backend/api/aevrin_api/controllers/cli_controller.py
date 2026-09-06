"""CLI upload handling: quota precheck, idempotent persistence of a locally
run scan, and the background AI review that annotates it afterwards.

A CLI upload is a client-reported result: the API cannot re-run the engine,
which needs a sandbox and the exact package the CLI launched. What it does
enforce is that an upload agrees with itself - see `_grade_contradicts_findings`
and ADR-033.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from aevrin_scanner_core import (
    Finding,
    Location,
    OwaspMcpCategory,
    Severity,
    ToolName,
)
from fastapi import BackgroundTasks, HTTPException, status
from pydantic import ValidationError

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import enforce_rate_limit
from aevrin_api.schemas import CliUploadFinding, CliUploadRequest, ScanOut
from aevrin_api.services.quota import check_and_increment_quota, would_exceed_quota
from aevrin_api.services.triage import triage_findings

logger = logging.getLogger("aevrin.cli_upload")


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
    )


async def precheck(user_id: str, db: SupabaseRest, settings: Settings) -> dict[str, bool]:
    exceeded = await would_exceed_quota(settings, db, user_id, "cli")
    if exceeded:
        raise exceeded
    return {"ok": True}


def _assert_id_is_reusable(persisted: dict[str, object], body: CliUploadRequest, user_id: str) -> None:
    """Client-generated IDs make network retries idempotent, but must never let
    an upload overwrite a dashboard/hook scan or reuse an ID for a different
    target."""
    same_upload = (
        persisted["user_id"] == user_id
        and persisted.get("source") == "cli"
        and persisted["target_type"] == body.target_type
        and persisted["target"] == body.target
    )
    if not same_upload:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Scan ID is already in use")


# Grades whose policy is ALLOW - the letters that tell someone they need not
# look. Kept here and not imported from the grade/policy mapping because this
# is not a scoring decision: it is the set of answers that would be actively
# misleading beside a serious finding.
_ALLOW_BAND = {"A", "B"}
# Worst first, so the message names the most serious contradiction. A set
# would sort alphabetically, which puts "critical" before "high" by accident
# rather than by meaning - and would quietly invert if a level were added.
_SERIOUS = ("critical", "high")


def _grade_contradicts_findings(
    grade: str | None, findings: Sequence[CliUploadFinding]
) -> str | None:
    """Does this upload disagree with itself? Returns why, or None.

    This deliberately does **not** recompute a grade. It asks a much weaker
    question that needs no severity weights and no band table: can the letter
    the client claimed and the findings the client attached both be true?

    An "A" or "B" resolves to an ALLOW policy - the hook stops prompting and
    the marketplace stops warning. A Critical or High finding in the same
    payload contradicts that outright, whatever arithmetic produced the
    letter. That combination is the shape a tampered CLI takes when it wants
    a dangerous server to install quietly, and it is not something a correct
    client can emit.
    """
    if not grade or grade.upper() not in _ALLOW_BAND:
        return None
    present = {f.severity.lower() for f in findings}
    worst = next((s for s in _SERIOUS if s in present), None)
    if worst is None:
        return None
    return (
        f"This scan reported grade {grade.upper()}, which allows the server to run "
        f"without review, while also reporting a {worst} finding. Those cannot both "
        "be true, so the result was not stored."
    )


def _scan_row(
    body: CliUploadRequest,
    user_id: str,
    risk_score: int | None,
    grade: str | None,
    now: datetime,
) -> dict[str, object]:
    return {
        "user_id": user_id,
        "target_type": body.target_type,
        "target": body.target,
        "status": body.status,
        "source": "cli",
        "risk_score": risk_score,
        "grade": grade,
        "mcp_detected": body.mcp_detected,
        "mcp_tools_declared": body.mcp_tools_declared,
        "unreliable_stages": body.unreliable_stages,
        "created_at": (body.created_at or now).isoformat(),
        "completed_at": (body.completed_at or now).isoformat(),
    }


def _stage_rows(body: CliUploadRequest, scan_id: UUID) -> list[dict[str, object]]:
    return [
        {
            "scan_id": str(scan_id),
            "name": s.name,
            "status": s.status,
            "error": s.error,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "finished_at": s.finished_at.isoformat() if s.finished_at else None,
        }
        for s in body.stages
    ]


def _finding_rows(body: CliUploadRequest, scan_id: UUID, user_id: str) -> list[dict[str, object]]:
    return [
        {
            "id": str(f.id),
            "scan_id": str(scan_id),
            "user_id": user_id,
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
            "raw": f.raw,
            **({"created_at": f.created_at.isoformat()} if f.created_at else {}),
        }
        for f in body.findings
    ]


def _hook_cache_row(
    body: CliUploadRequest,
    scan_id: UUID,
    user_id: str,
    risk_score: int | None,
    grade: str | None,
    now: datetime,
) -> dict[str, object]:
    return {
        "user_id": user_id,
        "target": body.target,
        "last_scan_id": str(scan_id),
        "last_risk_score": risk_score,
        "last_grade": grade,
        "last_status": body.status,
        "checked_at": (body.completed_at or now).isoformat(),
    }


async def upload_scan(
    body: CliUploadRequest,
    background: BackgroundTasks,
    user_id: str,
    db: SupabaseRest,
    settings: Settings,
) -> ScanOut:
    enforce_rate_limit(settings, "cli_upload", user_id, settings.cli_uploads_per_key_per_hour)
    scan_id = body.scan_id or uuid4()

    try:
        core_findings = [_to_core_finding(f, scan_id) for f in body.findings]
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    # Aevrin cannot re-run the engine here: a grade comes from launching the
    # server and reading its tools, and the API has neither the sandbox nor
    # the package version the CLI used. Re-deriving a letter from finding rows
    # alone would mean a second scoring algorithm, which is the duplication
    # ADR-033 exists to prevent. So a CLI upload is a client-reported result,
    # and `invocation_channel` records that.
    #
    # What the API *can* do without scoring anything is refuse an upload that
    # contradicts itself. Both checks below compare the client's own claims
    # against the client's own evidence; neither one computes a grade.
    if not body.mcp_tools_declared and body.grade:
        # A grade is a claim about tools that were read. No tools, no claim.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "This scan reported a grade without enumerating any tools. A grade "
                "describes tools that were read, so a scan that read none is "
                "incomplete rather than graded."
            ),
        )
    if incoherent := _grade_contradicts_findings(body.grade, body.findings):
        # Not a rubric: an ALLOW-band letter sitting beside the uploader's own
        # Critical finding is self-contradictory whatever arithmetic produced
        # it. Refused outright rather than stored with the grade quietly
        # dropped - a scan row that is ungraded for unexplained reasons is the
        # kind of silent degradation the pipeline's honesty rules forbid.
        logger.warning(
            "cli upload for user %s target %s refused: %s", user_id, body.target, incoherent
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=incoherent
        )

    reported_risk = body.risk_score
    reported_grade = body.grade

    existing = await db.select("scans", {"id": str(scan_id)})
    if existing:
        _assert_id_is_reusable(existing[0], body, user_id)
    else:
        # A retry carries the same client-generated scan ID. Repair/upsert its
        # related records without consuming a second quota credit or creating a
        # duplicate history row.
        await check_and_increment_quota(settings, db, user_id, "cli")

    now = datetime.now(UTC)
    scan_payload = _scan_row(body, user_id, reported_risk, reported_grade, now)
    if existing:
        scan_rows = await db.update("scans", {"id": str(scan_id), "user_id": user_id}, scan_payload)
    else:
        scan_rows = await db.insert("scans", {"id": str(scan_id), **scan_payload})

    if body.stages:
        await db.insert("scan_stages", _stage_rows(body, scan_id), upsert_on="scan_id,name")
    if body.findings:
        await db.insert("findings", _finding_rows(body, scan_id, user_id), upsert_on="id")
    await db.insert(
        "hook_cache",
        _hook_cache_row(body, scan_id, user_id, reported_risk, reported_grade, now),
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
            _triage_upload_best_effort, settings, db, user_id, scan_id, core_findings
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
