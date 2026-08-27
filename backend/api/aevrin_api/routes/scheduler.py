"""Endpoints an external scheduler calls on a timer.

Aevrin runs on AWS, so these are invoked by whatever is already scheduling
things there -- an EventBridge rule, a scheduled task, a cron entry hitting
the API. There is deliberately no scheduler, no worker, and no queue inside
this application: the platform already has one, and a second would be a second
thing to operate.

Authentication is a shared token rather than a session, because the caller is
a machine with no user behind it. It is compared in constant time and is
required: with no token configured these endpoints refuse everything, which is
the safe direction for something that can start scans.

Every one of these is safe to call more often than intended and safe to
re-run after a failure. Nothing here is destructive.
"""

from __future__ import annotations

import hmac
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from aevrin_api.config import Settings, get_settings
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import get_db
from aevrin_api.services.ai.provider_sync import sync_all_providers
from aevrin_api.services.marketplace.sync import listings_needing_scan, run_weekly_sync

logger = logging.getLogger("aevrin.scheduler")

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


def require_scheduler_token(
    settings: Annotated[Settings, Depends(get_settings)],
    x_scheduler_token: Annotated[str | None, Header()] = None,
) -> None:
    """Authenticate the scheduler.

    Fails closed when unconfigured. An unset token must not mean "anyone may
    trigger a catalogue-wide scan"; it means this capability is switched off.
    """
    if not settings.scheduler_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduled jobs are not enabled on this server.",
        )
    if not x_scheduler_token or not hmac.compare_digest(
        x_scheduler_token, settings.scheduler_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid scheduler token"
        )


@router.post("/registry-sync", dependencies=[Depends(require_scheduler_token)])
async def registry_sync(
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    full: Annotated[bool, Query()] = False,
) -> Any:
    """Pull the MCP Registry, refresh metadata, and recompute rankings.

    Intended weekly. Incremental by default: only servers the registry says
    have changed since the last successful run are fetched. `full=true`
    ignores that watermark.

    Returns a report rather than raising, even when the registry is
    unreachable. The catalogue stays online; it simply stops growing until the
    next run.
    """
    report = await run_weekly_sync(db, settings, full=full)
    return report.as_dict()


@router.post("/provider-sync", dependencies=[Depends(require_scheduler_token)])
async def provider_sync(
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Any:
    """Refresh the AI model catalogue from each provider.

    A provider with no configured catalogue credential is skipped and its
    previously synced models are left in place. A failed refresh never empties
    the catalogue: the last known-good list keeps serving.
    """
    report = await sync_all_providers(db, settings)
    return report.as_dict()


@router.get("/scan-queue", dependencies=[Depends(require_scheduler_token)])
async def scan_queue(
    db: Annotated[SupabaseRest, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Any:
    """Versions that exist but have never been scanned.

    A query, not a stored queue. The set of unscanned versions is derivable
    from the data at any moment, so keeping a separate list would only create
    something that could disagree with reality.
    """
    return await listings_needing_scan(db, limit=limit)
