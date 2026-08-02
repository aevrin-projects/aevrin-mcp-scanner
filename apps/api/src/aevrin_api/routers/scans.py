from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from aevrin_scanner_core import TargetType
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from ..config import Settings, get_settings
from ..db import SupabaseRest
from ..deps import enforce_rate_limit, get_current_user, get_db
from ..scan_service import start_scan
from ..schemas import CreateScanRequest, FindingOut, ScanOut, ScanStageOut
from ..security import AuthenticatedUser

router = APIRouter(prefix="/scans", tags=["scans"])


@router.post("", response_model=ScanOut, status_code=status.HTTP_201_CREATED)
async def create_scan(
    body: CreateScanRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ScanOut:
    enforce_rate_limit(settings, "scan_create", user.id, settings.scans_per_user_per_hour)

    scan_id = uuid4()
    rows = await db.insert(
        "scans",
        {
            "id": str(scan_id),
            "user_id": user.id,
            "target_type": body.target_type,
            "target": body.target,
            "status": "queued",
        },
    )
    background_tasks.add_task(
        start_scan, scan_id, user.id, TargetType(body.target_type), body.target, settings
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
