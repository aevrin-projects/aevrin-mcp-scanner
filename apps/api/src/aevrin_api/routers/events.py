"""Unauthenticated first-party analytics ingest.

Lives on the API rather than in the Next.js app deliberately: the write needs
the Supabase service-role key, and putting that key on the public-facing web
service would widen the blast radius of any SSRF or RCE there to full
database access. The API already holds it for legitimate reasons, so the
event is forwarded one hop instead.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field

from ..config import Settings, get_settings
from ..db import SupabaseRest
from ..deps import client_ip, get_db

router = APIRouter(prefix="/events", tags=["events"])
logger = logging.getLogger("aevrin.events")


class PageViewIn(BaseModel):
    path: str = Field(min_length=1, max_length=512)
    referrer: str | None = Field(default=None, max_length=512)
    country: str | None = Field(default=None, max_length=8)


def _visitor_hash(settings: Settings, ip: str, user_agent: str) -> str:
    """Salted hash of IP + user agent + today's date.

    The date in the input is what keeps this from being a tracker: the same
    person hashes to a different value tomorrow, so visits cannot be joined
    across days. It counts distinct visitors within one day and nothing more,
    and cannot be reversed to an IP.
    """
    salt = settings.api_key_pepper or "aevrin-analytics"
    day = datetime.now(UTC).date().isoformat()
    return hashlib.sha256(f"{salt}:{day}:{ip}:{user_agent}".encode()).hexdigest()[:32]


def _coarse_device(user_agent: str) -> str:
    ua = user_agent.lower()
    if "ipad" in ua or "tablet" in ua:
        return "tablet"
    if any(m in ua for m in ("mobi", "android", "iphone")):
        return "mobile"
    return "desktop"


@router.post("/pageview", status_code=status.HTTP_204_NO_CONTENT)
async def pageview(
    body: PageViewIn,
    request: Request,
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Always 204. A failed pageview must never surface to a visitor, and an
    analytics outage must never look like a broken site."""
    try:
        path = body.path
        # Founder movement through the admin panel isn't customer traffic and
        # would only skew the numbers it appears in.
        if path.startswith("/") and not path.startswith("/admin"):
            ua = request.headers.get("user-agent", "unknown")
            await db.insert(
                "page_views",
                {
                    "path": path,
                    "referrer": (body.referrer or None),
                    "country": body.country
                    or request.headers.get("cf-ipcountry")
                    or request.headers.get("x-vercel-ip-country"),
                    "device": _coarse_device(ua),
                    "visitor_hash": _visitor_hash(settings, client_ip(request), ua),
                },
            )
    except Exception:
        logger.warning("events: could not record pageview", exc_info=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
