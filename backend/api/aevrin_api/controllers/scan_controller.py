"""Scan lifecycle: create, list, read, delete, and per-scan child records."""

from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import suppress
from typing import Any, cast
from uuid import UUID, uuid4

from aevrin_scanner_core import TargetType
from fastapi import BackgroundTasks, HTTPException, UploadFile, status

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import enforce_rate_limit
from aevrin_api.schemas import CreateScanRequest, FindingOut, ScanOut, ScanStageOut
from aevrin_api.services.quota import check_and_increment_quota
from aevrin_api.services.scan import start_scan
from aevrin_api.services.source_upload import (
    MAX_ARCHIVE_BYTES,
    UnsafeArchive,
    extract_source_archive,
)
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


async def create_scan_from_upload(
    archive: UploadFile,
    target_label: str,
    background_tasks: BackgroundTasks,
    user_id: str,
    db: SupabaseRest,
    settings: Settings,
) -> ScanOut:
    """Scan a folder that only exists on someone's machine, here on the server.

    The scanners live in this image, which is why a dashboard scan of a GitHub
    repo works while the same folder on a laptop needs Docker and half a dozen
    binaries installed locally. This closes that gap: the CLI sends the source,
    the server runs the full tool set over it.

    Metered as a dashboard scan rather than a CLI one. The work happens here,
    on this instance's CPU, exactly like a scan started from the website; the
    CLI bucket is for scans the CLI actually performed itself.
    """
    enforce_rate_limit(settings, "scan_create", user_id, settings.scans_per_user_per_hour)
    await check_and_increment_quota(settings, db, user_id, "dashboard")

    tmp_archive = None
    try:
        tmp_archive = await _spool_upload(archive)
        source_dir = extract_source_archive(tmp_archive)
    except UnsafeArchive as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        if tmp_archive:
            # The extracted tree is what gets scanned; the archive itself has
            # no further use and is the larger of the two on disk.
            with suppress(OSError):
                os.remove(tmp_archive)

    scan_id = uuid4()
    # The label the person recognises, never the server temp path they have
    # never seen and which will not exist by the time they read the report.
    durable_target = target_label.strip()[:400] or "uploaded folder"
    rows = await db.insert(
        "scans",
        {
            "id": str(scan_id),
            "user_id": user_id,
            "target_type": TargetType.LOCAL_PATH.value,
            "target": durable_target,
            "status": "queued",
        },
    )
    background_tasks.add_task(
        _scan_uploaded_source,
        scan_id,
        user_id,
        source_dir,
        settings,
        durable_target,
    )
    return ScanOut(**rows[0])


async def _spool_upload(archive: UploadFile) -> str:
    """Streams the upload to disk, refusing it the moment it grows past the
    cap rather than after buffering the whole thing in memory."""
    fd, path = tempfile.mkstemp(suffix=".tar.gz", prefix="aevrin-upload-")
    written = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := await archive.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_ARCHIVE_BYTES:
                    raise UnsafeArchive(
                        f"archive is larger than {MAX_ARCHIVE_BYTES // (1024 * 1024)} MB"
                    )
                out.write(chunk)
    except BaseException:
        with suppress(OSError):
            os.remove(path)
        raise
    return path


async def _scan_uploaded_source(
    scan_id: UUID, user_id: str, source_dir: str, settings: Settings, durable_target: str
) -> None:
    """Runs the pipeline over the extracted tree and removes it afterwards,
    whatever happened. Nothing in that directory is ever executed; it is read
    by the scanners and then deleted."""
    try:
        await start_scan(
            scan_id, user_id, TargetType.LOCAL_PATH, source_dir, settings, durable_target
        )
    finally:
        shutil.rmtree(_upload_root(source_dir), ignore_errors=True)


def _upload_root(source_dir: str) -> str:
    """extract_source_archive unwraps a single top-level directory, so the
    directory that needs removing is usually the parent. Only ever the temp
    directory this created, matched on its own prefix so a bug here cannot
    delete anything else."""
    parent = os.path.dirname(source_dir)
    if os.path.basename(parent).startswith("aevrin-upload-"):
        return parent
    return source_dir


async def scan_diff(scan_id: UUID, user_id: str, db: SupabaseRest) -> dict[str, Any]:
    """What changed since the previous scan of the same target.

    Exists because a working fix read as a failure. A repository reported
    the same secret title in three files; fixing one correctly stopped it
    being reported, but the two untouched ones carry an identical title, so
    the result looked unchanged. This answers "did my fix work" directly
    instead of leaving it to be inferred from a list.
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
