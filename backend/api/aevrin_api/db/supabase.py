"""Thin async PostgREST client using the Supabase service-role key.

We talk to PostgREST directly instead of pulling in the full supabase-py SDK
since the surface we need (insert/select/update on a handful of tables) is small
enough that a direct client keeps behavior transparent and avoids an extra
dependency with its own retry/caching opinions.

Every call here runs as the service role, i.e. it bypasses RLS. Callers are
responsible for scoping queries to the right user_id themselves; this
module is the trusted-orchestrator path, not something exposed to clients
directly.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from aevrin_api.config import Settings

# PostgREST operator prefixes ("gte.", "in.", "not.in.", …). Used to tell a
# caller-supplied operator apart from a bare value that needs eq..
_HAS_OPERATOR = re.compile(r"^(not\.)?[a-z]+\.")


class SupabaseRestError(Exception):
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"PostgREST error {status_code}: {body}")


class SupabaseRest:
    def __init__(self, settings: Settings):
        self._base_url = f"{settings.supabase_url}/rest/v1"
        self._headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
        }

    async def insert(
        self, table: str, rows: dict[str, Any] | list[dict[str, Any]], *, upsert_on: str | None = None
    ) -> list[dict[str, Any]]:
        headers = {**self._headers, "Prefer": "return=representation"}
        params = {}
        if upsert_on:
            headers["Prefer"] += ",resolution=merge-duplicates"
            params["on_conflict"] = upsert_on
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._base_url}/{table}", headers=headers, json=rows, params=params
            )
        if resp.status_code >= 400:
            raise SupabaseRestError(resp.status_code, resp.text)
        result: list[dict[str, Any]] = resp.json()
        return result

    async def update(
        self, table: str, filters: dict[str, str], patch: dict[str, Any]
    ) -> list[dict[str, Any]]:
        headers = {**self._headers, "Prefer": "return=representation"}
        params = {k: f"eq.{v}" for k, v in filters.items()}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.patch(
                f"{self._base_url}/{table}", headers=headers, json=patch, params=params
            )
        if resp.status_code >= 400:
            raise SupabaseRestError(resp.status_code, resp.text)
        result: list[dict[str, Any]] = resp.json()
        return result

    async def select(
        self,
        table: str,
        filters: dict[str, str] | None = None,
        *,
        columns: str = "*",
        order: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        or_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"select": columns}
        for k, v in (filters or {}).items():
            # A value that already carries a PostgREST operator prefix
            # ("gte.2026-08-01", "in.(a,b)") is passed through untouched, so
            # callers can express ranges without every filter needing to be
            # equality. Bare values keep the previous eq. behaviour.
            params[k] = v if _HAS_OPERATOR.match(v) else f"eq.{v}"
        if or_filter:
            # PostgREST's `or=(a.eq.1,b.eq.2)`. Separate from `filters` because
            # it is one parameter holding a whole expression rather than a
            # column/value pair, and because callers must construct it
            # deliberately: everything inside it is OR'd, so folding it in with
            # the AND filters above would silently widen a query.
            params["or"] = or_filter
        if order:
            params["order"] = order
        if limit:
            params["limit"] = str(limit)
        if offset:
            params["offset"] = str(offset)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{self._base_url}/{table}", headers=self._headers, params=params)
        if resp.status_code >= 400:
            raise SupabaseRestError(resp.status_code, resp.text)
        result: list[dict[str, Any]] = resp.json()
        return result

    async def delete(self, table: str, filters: dict[str, str]) -> None:
        # Same operator pass-through as select() above, and for a sharper
        # reason: forcing eq. onto a value that already carried an operator
        # produced "eq.lt.2026-08-01", which PostgREST matches against
        # nothing. The delete then succeeded while removing no rows -- a
        # silent no-op, which for a retention sweep means the table simply
        # grows forever with nothing to show that it is not being pruned.
        params = {
            k: (v if _HAS_OPERATOR.match(v) else f"eq.{v}") for k, v in filters.items()
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(f"{self._base_url}/{table}", headers=self._headers, params=params)
        if resp.status_code >= 400:
            raise SupabaseRestError(resp.status_code, resp.text)

    async def rpc(self, fn: str, args: dict[str, Any]) -> Any:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{self._base_url}/rpc/{fn}", headers=self._headers, json=args)
        if resp.status_code >= 400:
            raise SupabaseRestError(resp.status_code, resp.text)
        return resp.json()
