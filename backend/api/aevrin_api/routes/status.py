"""The public status feed.

Unauthenticated by design: this is the data behind a status page, which is
the one thing that has to stay readable when someone cannot sign in. It
carries no user, organisation, or scan data -- only whether Aevrin's own
services answered, and how quickly.

Kept separate from `/health` because the two answer different questions.
`/health` is a liveness probe for a load balancer: is this process serving
right now. This is a history: what has been recorded over the trailing
window, including the days where nothing was recorded at all.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import get_db
from aevrin_api.services import status as status_service

router = APIRouter(prefix="/status", tags=["status"])


@router.get("/history")
async def status_history(
    db: Annotated[SupabaseRest, Depends(get_db)],
    days: Annotated[int, Query(ge=1, le=90)] = 30,
) -> Any:
    """Per-service daily availability over the trailing window.

    Every day in the window is returned, including ones with no checks. Those
    are `status: "no_data"` and are excluded from the uptime figure rather
    than counted as successes: the job that records checks calls this API, so
    an outage produces a gap rather than a failure row, and treating a gap as
    uptime would report a total outage as a perfect score.

    `uptime` is therefore "of the checks actually recorded", and
    `checks_recorded` is published beside it so the figure is never read as
    coverage it does not have.
    """
    return await status_service.history(db, days=days)
