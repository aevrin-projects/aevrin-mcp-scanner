"""Scan endpoints. HTTP contract only; the work is in controllers/scan_controller."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Response, UploadFile, status

from aevrin_api.config import Settings, get_settings
from aevrin_api.controllers import scan_controller
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import get_db, get_user_from_jwt_or_api_key
from aevrin_api.schemas import CreateScanRequest, FindingOut, ScanOut, ScanStageOut

router = APIRouter(prefix="/scans", tags=["scans"])

# JWT or API key: the dashboard and `aevrin scan --remote` both land here.
CurrentUser = Annotated[AuthenticatedUser, Depends(get_user_from_jwt_or_api_key)]
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


@router.post("/upload", response_model=ScanOut, status_code=status.HTTP_201_CREATED)
async def create_scan_from_upload(
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: Db,
    settings: Config,
    archive: Annotated[UploadFile, File(description="gzipped tar of the folder to scan")],
    target_label: Annotated[str, Form(description="path to show in the report")] = "",
) -> ScanOut:
    """Scan a local folder on the server instead of on the caller's machine.

    Every scanner is installed in this image, which is why a repository scan
    started from the website needs nothing locally. A folder on a laptop had
    no way to reach it, so scanning one required Docker and the whole tool set
    installed there instead. This accepts the source directly.

    The archive is extracted under strict limits and read; nothing inside it
    is ever executed, and the extracted copy is deleted when the scan ends.
    """
    return await scan_controller.create_scan_from_upload(
        archive, target_label, background_tasks, user.id, db, settings
    )


@router.get("/{scan_id}/diff")
async def scan_diff(scan_id: UUID, user: CurrentUser, db: Db) -> dict[str, Any]:
    """What changed since the previous scan of the same target.

    Exists because a working fix read as a failure. A repository reported
    the same secret title in three files; fixing one correctly stopped it
    being reported, but the two untouched ones carry an identical title, so
    the result looked unchanged. This answers "did my fix work" directly
    instead of leaving it to be inferred from a list.
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
