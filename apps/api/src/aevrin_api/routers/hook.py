"""Backs the Claude Code PreToolUse hook (apps/hook). The hook process
itself implements the decision logic locally (never blocks synchronously on
a live scan) — this endpoint just answers "what do we already know about
this target" and, on a cache miss, kicks off a background scan so the
*next* check has an answer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from aevrin_scanner_core import TargetType
from fastapi import APIRouter, BackgroundTasks, Depends, Query

from ..config import Settings, get_settings
from ..db import SupabaseRest
from ..deps import enforce_rate_limit, get_api_key_user, get_db
from ..quota import QuotaExceeded, check_and_increment_quota
from ..scan_service import start_scan
from ..schemas import HookCacheResponse, HookOverrideRequest, HookOverrideResponse
from ..security import AuthenticatedUser

router = APIRouter(prefix="/hook", tags=["hook"])

_BLOCKING_SEVERITIES = ("critical", "high")
_OVERRIDE_TTL_SECONDS = 600  # long enough for the person to retry the same install right after


@router.post("/override", response_model=HookOverrideResponse)
async def create_override(
    body: HookOverrideRequest,
    user: Annotated[AuthenticatedUser, Depends(get_api_key_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HookOverrideResponse:
    """Backs `aevrin hook allow <target>` — the "install anyway" path. A
    person who saw the hook's block reason and decided to proceed
    shouldn't have to disable the hook entirely to do it."""
    enforce_rate_limit(settings, "hook_override", user.id, 30)
    expires_at = datetime.now(UTC) + timedelta(seconds=_OVERRIDE_TTL_SECONDS)
    await db.insert("hook_overrides", {"user_id": user.id, "target": body.target, "expires_at": expires_at.isoformat()})
    return HookOverrideResponse(expires_at=expires_at)


@router.get("/cache", response_model=HookCacheResponse)
async def check_cache(
    background_tasks: BackgroundTasks,
    target: Annotated[str, Query(min_length=1, max_length=8000)],
    user: Annotated[AuthenticatedUser, Depends(get_api_key_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    target_type: str = "github_repo",
) -> HookCacheResponse:
    enforce_rate_limit(settings, "hook_check", user.id, settings.scans_per_user_per_hour * 6)

    cached = await db.select("hook_cache", {"user_id": user.id, "target": target})
    if not cached:
        try:
            await check_and_increment_quota(settings, db, user.id, "hook")
        except QuotaExceeded as exc:
            # Never a bare refusal — addendum §10 requires the same
            # what-happened/when-it-resets/where-to-upgrade shape the CLI
            # and dashboard get, surfaced through the hook's own decision
            # logic rather than an HTTP error (the hook fails open on
            # errors, but a quota refusal is a deliberate decision, not a
            # failure, so it must not look like one).
            return HookCacheResponse(
                decision="quota_exceeded", quota_resets_at=exc.resets_at, upgrade_url=exc.upgrade_url
            )

        scan_id = uuid4()
        await db.insert(
            "scans",
            {
                "id": str(scan_id),
                "user_id": user.id,
                "target_type": target_type,
                "target": target,
                "status": "queued",
            },
        )
        background_tasks.add_task(
            start_scan, scan_id, user.id, TargetType(target_type), target, settings
        )
        return HookCacheResponse(decision="allow_unscanned")

    row = cached[0]
    findings_summary: list[dict[str, object]] = []
    decision = "allow_clean"
    if row.get("last_scan_id"):
        blocking = await db.select(
            "findings",
            {"scan_id": row["last_scan_id"], "user_id": user.id},
        )
        blocking = [
            f for f in blocking
            if f["severity"] in _BLOCKING_SEVERITIES and not f["not_tested"] and f["triage_status"] != "false_positive"
        ]
        if blocking:
            decision = "block"
            # file_path/line_start/remediation give Claude (running in the
            # same session the hook just blocked) enough to actually locate
            # and fix the flagged code, not just know it exists.
            findings_summary = [
                {
                    "id": f["id"],
                    "title": f["title"],
                    "severity": f["severity"],
                    "owasp_category": f["owasp_category"],
                    "file_path": f.get("file_path"),
                    "line_start": f.get("line_start"),
                    "remediation": f.get("remediation"),
                }
                for f in blocking
            ]
        elif row.get("last_status") == "incomplete":
            # The scan behind this cache entry couldn't actually run its
            # tools (Docker down, missing binary, no network) — an empty
            # findings list here does NOT mean clean, so this must not fall
            # through to allow_clean the way a genuinely clean scan would.
            decision = "block_incomplete"

        if decision in ("block", "block_incomplete"):
            overrides = await db.select("hook_overrides", {"user_id": user.id, "target": target})
            now_iso = datetime.now(UTC).isoformat()
            if any(o["expires_at"] > now_iso for o in overrides):
                decision = "allow_override"

    return HookCacheResponse(
        decision=decision,
        score=row.get("last_score"),
        scan_id=row.get("last_scan_id"),
        checked_at=row.get("checked_at"),
        findings_summary=findings_summary,
    )
