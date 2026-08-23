"""Hook decision logic: what we already know about a target, and what to do
when we know nothing yet.

The hook process makes the final call locally; this decides what to tell it.
The contract and the surrounding rationale live on routes/hook.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from aevrin_scanner_core import TargetType, is_autofix_eligible
from fastapi import BackgroundTasks

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import enforce_rate_limit
from aevrin_api.schemas import HookCacheResponse, HookOverrideRequest, HookOverrideResponse
from aevrin_api.services.autofix import finding_from_row
from aevrin_api.services.quota import (
    QuotaExceeded,
    check_and_increment_quota,
    effective_tier,
    get_or_create_account,
)
from aevrin_api.services.scan import start_scan
from aevrin_api.services.targets import stored_target

_BLOCKING_SEVERITIES = ("critical", "high")
_OVERRIDE_TTL_SECONDS = 600  # long enough for the person to retry the same install right after


async def create_override(
    body: HookOverrideRequest, user_id: str, db: SupabaseRest, settings: Settings
) -> HookOverrideResponse:
    enforce_rate_limit(settings, "hook_override", user_id, 30)
    expires_at = datetime.now(UTC) + timedelta(seconds=_OVERRIDE_TTL_SECONDS)
    await db.insert(
        "hook_overrides",
        {"user_id": user_id, "target": body.target, "expires_at": expires_at.isoformat()},
    )
    return HookOverrideResponse(expires_at=expires_at)


def _finding_summary(f: dict[str, object]) -> dict[str, object]:
    """file_path/line_start/remediation give Claude (running in the same session
    the hook just blocked) enough to actually locate and fix the flagged code,
    not just know it exists."""
    return {
        "id": f["id"],
        "title": f["title"],
        "severity": f["severity"],
        "owasp_category": f["owasp_category"],
        "file_path": f.get("file_path"),
        "line_start": f.get("line_start"),
        "remediation": f.get("remediation"),
        "autofix_eligible": is_autofix_eligible(finding_from_row(f))[0],
    }


async def _autofix_hint(db: SupabaseRest, user_id: str) -> str:
    """A real conversion moment: tell the person right where the block happens,
    not just on the pricing page, when an auto-fix could clear this without
    hand-editing anything."""
    account = await get_or_create_account(db, user_id)
    if effective_tier(account) in ("pro", "team"):
        return (
            "One or more of these findings can be auto-fixed; run `aevrin fix <finding id>` "
            "to generate and open a pull request."
        )
    return (
        "One or more of these findings can be auto-fixed on Pro/Team. Aevrin drafts a patch, "
        "re-verifies it against the scanner, and opens a pull request for you."
    )


async def _queue_first_scan(
    background_tasks: BackgroundTasks,
    target: str,
    durable_target: str,
    target_type: str,
    user_id: str,
    db: SupabaseRest,
    settings: Settings,
) -> HookCacheResponse:
    """Nothing cached for this target yet: spend a hook credit, record a queued
    scan, and let the install proceed while it runs."""
    try:
        await check_and_increment_quota(settings, db, user_id, "hook")
    except QuotaExceeded as exc:
        # Never a bare refusal: the same what-happened / when-it-resets /
        # where-to-upgrade shape the CLI and dashboard get, surfaced through
        # the hook's own decision logic rather than an HTTP error. The hook
        # fails open on errors, but a quota refusal is a deliberate decision,
        # not a failure, so it must not look like one.
        return HookCacheResponse(
            decision="quota_exceeded",
            quota_resets_at=exc.resets_at,
            upgrade_url=exc.upgrade_url,
            target_key=durable_target,
        )

    scan_id = uuid4()
    await db.insert(
        "scans",
        {
            "id": str(scan_id),
            "user_id": user_id,
            "target_type": target_type,
            "target": durable_target,
            "status": "queued",
            "source": "hook",
        },
    )
    background_tasks.add_task(
        start_scan, scan_id, user_id, TargetType(target_type), target, settings, durable_target
    )
    return HookCacheResponse(decision="allow_unscanned", target_key=durable_target)


async def _decide_from_cache(
    row: dict[str, object], durable_target: str, user_id: str, db: SupabaseRest
) -> tuple[str, list[dict[str, object]], str | None]:
    """Turns the cached scan into a hook decision, honouring any active
    install-anyway override. Returns (decision, findings_summary, autofix_hint).
    """
    if not row.get("last_scan_id"):
        return "allow_clean", [], None

    findings = await db.select(
        "findings", {"scan_id": str(row["last_scan_id"]), "user_id": user_id}
    )
    blocking = [
        f
        for f in findings
        if f["severity"] in _BLOCKING_SEVERITIES
        and not f["not_tested"]
        and f["triage_status"] == "open"
    ]

    decision = "allow_clean"
    summary: list[dict[str, object]] = []
    hint: str | None = None
    if blocking:
        decision = "block"
        summary = [_finding_summary(f) for f in blocking]
        if any(f["autofix_eligible"] for f in summary):
            hint = await _autofix_hint(db, user_id)
    elif row.get("last_status") == "incomplete":
        # The scan behind this cache entry couldn't actually run its tools
        # (Docker down, missing binary, no network), an empty findings list
        # here does NOT mean clean, so this must not fall through to
        # allow_clean the way a genuinely clean scan would.
        decision = "block_incomplete"

    if decision in ("block", "block_incomplete"):
        overrides = await db.select("hook_overrides", {"user_id": user_id, "target": durable_target})
        now_iso = datetime.now(UTC).isoformat()
        if any(o["expires_at"] > now_iso for o in overrides):
            decision = "allow_override"

    return decision, summary, hint


async def check_cache(
    background_tasks: BackgroundTasks,
    target: str,
    target_type: str,
    user_id: str,
    db: SupabaseRest,
    settings: Settings,
) -> HookCacheResponse:
    enforce_rate_limit(settings, "hook_check", user_id, settings.scans_per_user_per_hour * 6)
    durable_target = stored_target(target_type, target)

    cached = await db.select("hook_cache", {"user_id": user_id, "target": durable_target})
    if not cached:
        return await _queue_first_scan(
            background_tasks, target, durable_target, target_type, user_id, db, settings
        )

    row = cached[0]
    decision, findings_summary, autofix_hint = await _decide_from_cache(
        row, durable_target, user_id, db
    )

    return HookCacheResponse(
        decision=decision,
        score=row.get("last_score"),
        scan_id=row.get("last_scan_id"),
        checked_at=row.get("checked_at"),
        findings_summary=findings_summary,
        target_key=durable_target,
        autofix_hint=autofix_hint,
    )
