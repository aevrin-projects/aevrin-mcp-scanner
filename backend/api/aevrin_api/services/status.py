"""Availability checks and the history the public status page reads.

The rule this module exists to enforce is stated once, here, because every
function below depends on it: **a missing check is not a passing check.**

The job that records checks reaches Aevrin over HTTP. When the API is down,
that job fails and writes nothing, so an outage leaves a *gap* rather than a
row saying "down". Computing uptime as `ok / recorded` would therefore score
a total outage as 100%, which is worse than showing nothing at all. Days with
no checks are reported as `no_data` and excluded from the uptime numerator
and denominator alike, and the payload carries the recorded-check count so a
reader can see how much the figure is actually based on.

Latency is stored only for successful checks. The time spent timing out is
not a latency measurement, and averaging it in would render an outage as a
slow day.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest

logger = logging.getLogger("aevrin.status")

# Kept in sync with the check constraint on service_checks.service.
SERVICES: dict[str, str] = {
    "api": "API",
    "auth": "Authentication",
    "web": "Web",
    "defectdojo": "OWASP-mapped reporting workspace",
}

# How long raw checks are kept. Slightly longer than the 30-day window the
# page shows, so a rollup at the edge of the window still has its rows.
RETENTION_DAYS = 35

DayStatus = str  # "operational" | "degraded" | "down" | "no_data"


# --------------------------------------------------------------------------
# Probing


async def _probe(
    client: httpx.AsyncClient, url: str, headers: dict[str, str] | None = None
) -> tuple[bool, int | None, str | None]:
    """One request. Returns (ok, latency_ms, detail).

    Never raises: a probe that threw would abort the whole run and lose the
    results of every other service checked alongside it.
    """
    try:
        response = await client.get(url, headers=headers, timeout=10.0)
    except httpx.TimeoutException:
        return False, None, "timeout"
    except httpx.HTTPError as exc:
        # Only the exception class, never the message: a message can carry the
        # request URL with a query string in it.
        return False, None, type(exc).__name__
    ok = response.is_success
    latency = int(response.elapsed.total_seconds() * 1000) if ok else None
    return ok, latency, None if ok else f"status {response.status_code}"


async def run_checks(db: SupabaseRest, settings: Settings) -> dict[str, Any]:
    """Probe every configured service and record one row each.

    `web` and `api` are recorded as reachable without a request. That is not a
    courtesy: this function runs inside the API process, reached over HTTP
    through the same edge that serves the site, so both were demonstrably up
    at this instant. What it deliberately does *not* do is infer anything
    about the moments it did not run -- see the module docstring.
    """
    rows: list[dict[str, Any]] = [
        {"service": "api", "ok": True, "latency_ms": None, "detail": None},
        {"service": "web", "ok": True, "latency_ms": None, "detail": None},
    ]

    async with httpx.AsyncClient(follow_redirects=True) as client:
        ok, latency, detail = await _probe(
            client,
            f"{settings.supabase_url}/auth/v1/health",
            headers={"apikey": settings.supabase_anon_key},
        )
        rows.append({"service": "auth", "ok": ok, "latency_ms": latency, "detail": detail})

        # Only checked when it is actually deployed. Recording a component
        # nobody configured as down would make a healthy system look degraded.
        dojo_url = getattr(settings, "defectdojo_url", None)
        if dojo_url:
            ok, latency, detail = await _probe(client, f"{dojo_url}/login")
            rows.append(
                {"service": "defectdojo", "ok": ok, "latency_ms": latency, "detail": detail}
            )

    await db.insert("service_checks", rows)
    pruned = await _prune(db)
    logger.info("uptime_check_recorded services=%d pruned=%s", len(rows), pruned)
    return {
        "recorded": [{"service": r["service"], "ok": r["ok"]} for r in rows],
        "pruned_before": pruned,
    }


async def _prune(db: SupabaseRest) -> str:
    """Drop checks older than the retention window.

    A status page needs a bounded window, not an archive, and an unbounded
    append-only table is a slow leak that only shows up months later.
    """
    cutoff = (datetime.now(UTC) - timedelta(days=RETENTION_DAYS)).isoformat()
    await db.delete("service_checks", {"checked_at": f"lt.{cutoff}"})
    return cutoff


# --------------------------------------------------------------------------
# History


def _day_status(total: int, ok: int) -> DayStatus:
    if total == 0:
        return "no_data"
    if ok == total:
        return "operational"
    if ok == 0:
        return "down"
    return "degraded"


async def history(db: SupabaseRest, *, days: int = 30) -> dict[str, Any]:
    """Per-service daily rollup over the trailing `days` days.

    Every day in the window is present, including days with no checks, so the
    caller renders a continuous strip and cannot mistake a gap for the series
    simply having started later.
    """
    since = datetime.now(UTC) - timedelta(days=days - 1)
    window_start = since.date()

    rows = await db.select(
        "service_checks",
        {"checked_at": f"gte.{window_start.isoformat()}"},
        columns="service,ok,latency_ms,checked_at",
        order="checked_at.asc",
        limit=20000,
    )

    # service -> date -> [total, ok, latency_sum, latency_n]
    buckets: dict[str, dict[date, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))
    for row in rows:
        raw = row.get("checked_at")
        if not isinstance(raw, str):
            continue
        try:
            # fromisoformat handles the trailing "Z" natively on 3.11+.
            when = datetime.fromisoformat(raw).astimezone(UTC).date()
        except ValueError:
            continue
        bucket = buckets[row["service"]][when]
        bucket[0] += 1
        if row.get("ok"):
            bucket[1] += 1
        latency = row.get("latency_ms")
        if isinstance(latency, int):
            bucket[2] += latency
            bucket[3] += 1

    window = [window_start + timedelta(days=offset) for offset in range(days)]

    services: list[dict[str, Any]] = []
    for service_id, label in SERVICES.items():
        per_day = buckets.get(service_id, {})
        # A service that has never been checked is omitted rather than shown
        # as a fully blank row: defectdojo is optional, and an empty strip
        # for something nobody deployed is noise, not information.
        if not per_day:
            continue

        day_entries = []
        recorded = 0
        succeeded = 0
        for day in window:
            total, ok, latency_sum, latency_n = per_day.get(day, [0, 0, 0, 0])
            recorded += total
            succeeded += ok
            day_entries.append(
                {
                    "date": day.isoformat(),
                    "status": _day_status(total, ok),
                    "checks": total,
                    "ok": ok,
                    "uptime": round(ok / total * 100, 2) if total else None,
                    "avg_latency_ms": round(latency_sum / latency_n) if latency_n else None,
                }
            )

        services.append(
            {
                "id": service_id,
                "name": label,
                "days": day_entries,
                # Of recorded checks only, and the count is published beside it
                # so the figure is never read as coverage it does not have.
                "uptime": round(succeeded / recorded * 100, 2) if recorded else None,
                "checks_recorded": recorded,
                "days_with_data": sum(1 for d in day_entries if d["status"] != "no_data"),
            }
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "window_days": days,
        "services": services,
    }
