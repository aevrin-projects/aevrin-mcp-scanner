"""Pageview ingest: derive the coarse, non-identifying columns and write one
row. Swallows its own failures by design; see the route for why.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.schemas.events import PageViewIn

logger = logging.getLogger("aevrin.events")


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


async def record_pageview(
    body: PageViewIn,
    *,
    ip: str,
    user_agent: str,
    country_header: str | None,
    db: SupabaseRest,
    settings: Settings,
) -> None:
    try:
        # Founder movement through the admin panel isn't customer traffic and
        # would only skew the numbers it appears in.
        if not body.path.startswith("/") or body.path.startswith("/admin"):
            return
        await db.insert(
            "page_views",
            {
                "path": body.path,
                "referrer": (body.referrer or None),
                "country": body.country or country_header,
                "device": _coarse_device(user_agent),
                "visitor_hash": _visitor_hash(settings, ip, user_agent),
            },
        )
    except Exception:
        logger.warning("events: could not record pageview", exc_info=True)
