from __future__ import annotations

import hashlib
from typing import Annotated
from uuid import UUID, uuid4

from aevrin_scanner_core import TargetType
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status

from ..config import Settings, get_settings
from ..db import SupabaseRest
from ..deps import enforce_rate_limit, get_current_user, get_db
from ..quota import check_and_increment_quota
from ..scan_service import start_scan
from ..schemas import CreateScanRequest, FindingOut, ScanOut, ScanStageOut
from ..security import AuthenticatedUser

router = APIRouter(prefix="/scans", tags=["scans"])


def _stored_target(target_type: str, target: str) -> str:
    if target_type != "config_paste":
        return target
    digest = hashlib.sha256(target.encode()).hexdigest()[:12]
    return f"Pasted MCP configuration · {digest}"


@router.post("", response_model=ScanOut, status_code=status.HTTP_201_CREATED)
async def create_scan(
    body: CreateScanRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ScanOut:
    enforce_rate_limit(settings, "scan_create", user.id, settings.scans_per_user_per_hour)
    await check_and_increment_quota(settings, db, user.id, "dashboard")

    scan_id = uuid4()
    stored_target = _stored_target(body.target_type, body.target)
    rows = await db.insert(
        "scans",
        {
            "id": str(scan_id),
            "user_id": user.id,
            "target_type": body.target_type,
            "target": stored_target,
            "status": "queued",
        },
    )
    background_tasks.add_task(
        start_scan,
        scan_id,
        user.id,
        TargetType(body.target_type),
        body.target,
        settings,
        stored_target,
    )
    return ScanOut(**rows[0])


@router.get("", response_model=list[ScanOut])
async def list_scans(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
) -> list[ScanOut]:
    rows = await db.select(
        "scans", {"user_id": user.id}, order="created_at.desc", limit=25
    )
    return [ScanOut(**r) for r in rows]


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_scan_history(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
) -> Response:
    # Findings, stages, and related scan records are deleted by their existing
    # foreign-key cascades. The user_id filter is mandatory because this client
    # runs with the Supabase service role and therefore bypasses RLS.
    active = await db.select("scans", {"user_id": user.id}, columns="id,status")
    if any(row["status"] in {"queued", "running"} for row in active):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wait for active scans to finish before clearing history",
        )
    # A cache row without its `last_scan_id` would otherwise look clean to
    # the hook after the scan FK is set to null. Remove those cached verdicts
    # first so the next hook check performs a fresh scan.
    await db.delete("hook_cache", {"user_id": user.id})
    await db.delete("scans", {"user_id": user.id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{scan_id}", response_model=ScanOut)
async def get_scan(
    scan_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
) -> ScanOut:
    rows = await db.select("scans", {"id": str(scan_id), "user_id": user.id})
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
    return ScanOut(**rows[0])


@router.delete("/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scan(
    scan_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
) -> Response:
    rows = await db.select("scans", {"id": str(scan_id), "user_id": user.id})
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
    if rows[0]["status"] in {"queued", "running"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wait for this scan to finish before deleting it",
        )
    await db.delete("hook_cache", {"last_scan_id": str(scan_id), "user_id": user.id})
    await db.delete("scans", {"id": str(scan_id), "user_id": user.id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{scan_id}/stages", response_model=list[ScanStageOut])
async def get_scan_stages(
    scan_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
) -> list[ScanStageOut]:
    await _assert_owns_scan(db, scan_id, user.id)
    rows = await db.select("scan_stages", {"scan_id": str(scan_id)})
    return [ScanStageOut(**r) for r in rows]


@router.get("/{scan_id}/findings", response_model=list[FindingOut])
async def get_scan_findings(
    scan_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
) -> list[FindingOut]:
    rows = await db.select("findings", {"scan_id": str(scan_id), "user_id": user.id})
    return [FindingOut(**r) for r in rows]


async def _assert_owns_scan(db: SupabaseRest, scan_id: UUID, user_id: str) -> None:
    rows = await db.select("scans", {"id": str(scan_id), "user_id": user_id})
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
