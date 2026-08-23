"""Scan endpoints. HTTP contract only; the work is in controllers/scan_controller."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status

from aevrin_api.config import Settings, get_settings
from aevrin_api.controllers import scan_controller
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import get_current_user, get_db
from aevrin_api.schemas import CreateScanRequest, FindingOut, ScanOut, ScanStageOut

router = APIRouter(prefix="/scans", tags=["scans"])

CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Db = Annotated[SupabaseRest, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


@router.post("", response_model=ScanOut, status_code=status.HTTP_201_CREATED)
async def create_scan(
    body: CreateScanRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> ScanOut:
    return await scan_controller.create_scan(body, background_tasks, user.id, db, settings)


@router.get("/{scan_id}/diff")
async def scan_diff(scan_id: UUID, user: CurrentUser, db: Db) -> dict[str, Any]:
    """What changed since the previous scan of the same target.

    Exists because a working fix read as a failure. A repository reported
    the same secret title in three files; Fix It resolved one and the
    rescan correctly stopped reporting it, but the two untouched ones carry
    an identical title, so the result looked unchanged. This answers "did my
    fix work" directly instead of leaving it to be inferred from a list.
    """
    return await scan_controller.scan_diff(scan_id, user.id, db)


@router.get("", response_model=list[ScanOut])
async def list_scans(user: CurrentUser, db: Db) -> list[ScanOut]:
    return await scan_controller.list_scans(user.id, db)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_scan_history(user: CurrentUser, db: Db) -> Response:
    await scan_controller.clear_scan_history(user.id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{scan_id}", response_model=ScanOut)
async def get_scan(scan_id: UUID, user: CurrentUser, db: Db) -> ScanOut:
    return await scan_controller.get_scan(scan_id, user.id, db)


@router.delete("/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scan(scan_id: UUID, user: CurrentUser, db: Db) -> Response:
    await scan_controller.delete_scan(scan_id, user.id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{scan_id}/stages", response_model=list[ScanStageOut])
async def get_scan_stages(scan_id: UUID, user: CurrentUser, db: Db) -> list[ScanStageOut]:
    return await scan_controller.get_scan_stages(scan_id, user.id, db)


@router.get("/{scan_id}/findings", response_model=list[FindingOut])
async def get_scan_findings(scan_id: UUID, user: CurrentUser, db: Db) -> list[FindingOut]:
    return await scan_controller.get_scan_findings(scan_id, user.id, db)
