"""Scan lifecycle: create, list, read, delete, and per-scan child records."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID, uuid4

from aevrin_scanner_core import TargetType
from fastapi import BackgroundTasks, HTTPException, status

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import enforce_rate_limit
from aevrin_api.schemas import CreateScanRequest, FindingOut, ScanOut, ScanStageOut
from aevrin_api.services.quota import check_and_increment_quota
from aevrin_api.services.scan import start_scan
from aevrin_api.services.targets import stored_target

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

_SCAN_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")


def _finding_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        # A finding excluded from scoring (test fixture, untested category)
        # is context, not a result, so it sinks below everything real
        # regardless of the severity the scanner gave it.
        bool(row.get("not_tested")) or bool(row.get("excluded_path")),
        _SEVERITY_RANK.get(str(row.get("severity")), 9),
        str(row.get("file_path") or "\uffff"),  # locationless findings last
        int(row.get("line_start") or 0),
        str(row.get("title") or ""),
    )


async def _assert_owns_scan(db: SupabaseRest, scan_id: UUID, user_id: str) -> None:
    rows = await db.select("scans", {"id": str(scan_id), "user_id": user_id})
    if not rows:
        raise _SCAN_NOT_FOUND


async def create_scan(
    body: CreateScanRequest,
    background_tasks: BackgroundTasks,
    user_id: str,
    db: SupabaseRest,
    settings: Settings,
) -> ScanOut:
    enforce_rate_limit(settings, "scan_create", user_id, settings.scans_per_user_per_hour)
    await check_and_increment_quota(settings, db, user_id, "dashboard")

    scan_id = uuid4()
    durable_target = stored_target(body.target_type, body.target)
    rows = await db.insert(
        "scans",
        {
            "id": str(scan_id),
            "user_id": user_id,
            "target_type": body.target_type,
            "target": durable_target,
            "status": "queued",
        },
    )
    background_tasks.add_task(
        start_scan,
        scan_id,
        user_id,
        TargetType(body.target_type),
        body.target,
        settings,
        durable_target,
    )
    return ScanOut(**rows[0])


async def scan_diff(scan_id: UUID, user_id: str, db: SupabaseRest) -> dict[str, Any]:
    """What changed since the previous scan of the same target.

    Exists because a working fix read as a failure. A repository reported
    the same secret title in three files; Fix It resolved one and the
    rescan correctly stopped reporting it, but the two untouched ones carry
    an identical title, so the result looked unchanged. This answers "did my
    fix work" directly instead of leaving it to be inferred from a list.
    """
    # Shape guaranteed by the scan_diff SQL function, not by db.rpc, which
    # returns the response body untyped.
    return cast(dict[str, Any], await db.rpc("scan_diff", {"p_scan_id": str(scan_id), "p_user_id": user_id}))


async def list_scans(user_id: str, db: SupabaseRest) -> list[ScanOut]:
    rows = await db.select("scans", {"user_id": user_id}, order="created_at.desc", limit=25)
    return [ScanOut(**r) for r in rows]


async def clear_scan_history(user_id: str, db: SupabaseRest) -> None:
    # Findings, stages, and related scan records are deleted by their existing
    # foreign-key cascades. The user_id filter is mandatory because this client
    # runs with the Supabase service role and therefore bypasses RLS.
    active = await db.select("scans", {"user_id": user_id}, columns="id,status")
    if any(row["status"] in {"queued", "running"} for row in active):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wait for active scans to finish before clearing history",
        )
    # A cache row without its `last_scan_id` would otherwise look clean to
    # the hook after the scan FK is set to null. Remove those cached verdicts
    # first so the next hook check performs a fresh scan.
    await db.delete("hook_cache", {"user_id": user_id})
    await db.delete("scans", {"user_id": user_id})


async def get_scan(scan_id: UUID, user_id: str, db: SupabaseRest) -> ScanOut:
    rows = await db.select("scans", {"id": str(scan_id), "user_id": user_id})
    if not rows:
        raise _SCAN_NOT_FOUND
    return ScanOut(**rows[0])


async def delete_scan(scan_id: UUID, user_id: str, db: SupabaseRest) -> None:
    rows = await db.select("scans", {"id": str(scan_id), "user_id": user_id})
    if not rows:
        raise _SCAN_NOT_FOUND
    if rows[0]["status"] in {"queued", "running"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wait for this scan to finish before deleting it",
        )
    await db.delete("hook_cache", {"last_scan_id": str(scan_id), "user_id": user_id})
    await db.delete("scans", {"id": str(scan_id), "user_id": user_id})


async def get_scan_stages(scan_id: UUID, user_id: str, db: SupabaseRest) -> list[ScanStageOut]:
    await _assert_owns_scan(db, scan_id, user_id)
    rows = await db.select("scan_stages", {"scan_id": str(scan_id)})
    return [ScanStageOut(**r) for r in rows]


async def get_scan_findings(scan_id: UUID, user_id: str, db: SupabaseRest) -> list[FindingOut]:
    rows = await db.select("findings", {"scan_id": str(scan_id), "user_id": user_id})
    # Most severe first, then grouped by file. Postgres can't order by this
    # without a custom type, and the previous insertion order meant whichever
    # scanner happened to finish first led the list, so a critical could sit
    # below a dozen lows on the one screen that has to convey urgency.
    rows.sort(key=_finding_sort_key)
    return [FindingOut(**r) for r in rows]
