"""Unauthenticated first-party analytics ingest.

Lives on the API rather than in the Next.js app deliberately: the write needs
the Supabase service-role key, and putting that key on the public-facing web
service would widen the blast radius of any SSRF or RCE there to full
database access. The API already holds it for legitimate reasons, so the
event is forwarded one hop instead.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from aevrin_api.config import Settings, get_settings
from aevrin_api.controllers import event_controller
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import client_ip, get_db
from aevrin_api.schemas.events import PageViewIn

router = APIRouter(prefix="/events", tags=["events"])


@router.post("/pageview", status_code=status.HTTP_204_NO_CONTENT)
async def pageview(
    body: PageViewIn,
    request: Request,
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Always 204. A failed pageview must never surface to a visitor, and an
    analytics outage must never look like a broken site."""
    await event_controller.record_pageview(
        body,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent", "unknown"),
        country_header=(
            request.headers.get("cf-ipcountry") or request.headers.get("x-vercel-ip-country")
        ),
        db=db,
        settings=settings,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
