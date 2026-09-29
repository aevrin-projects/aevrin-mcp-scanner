"""An update's filters are equalities, whatever the value looks like.

`select` and `delete` pass a value that starts with an operator ("is.null",
"gt.2026-01-01") straight through. `update` must not: it is a write, and many
of its filters are keyed on values that arrived in a request. A slug or id
that happened to read "neq.x" would otherwise update every other row.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import aevrin_api.db.supabase as module
from aevrin_api.db.supabase import SupabaseRest


class _Settings:
    supabase_url = "https://test.supabase.co"
    supabase_service_role_key = "service-key"


def _captured_update_params(monkeypatch: pytest.MonkeyPatch, **call: Any) -> dict[str, str]:
    captured: dict[str, str] = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json() -> list[dict[str, Any]]:
            return []

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        async def patch(self, url: str, headers: Any = None, json: Any = None, params: Any = None) -> _Resp:
            captured.update(params or {})
            return _Resp()

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda *a, **k: _Client())
    db = SupabaseRest(_Settings())  # type: ignore[arg-type]
    asyncio.run(db.update("mcp_listings", call["filters"], {"title": "x"}, **call.get("kwargs", {})))
    return captured


def test_an_operator_shaped_value_is_matched_literally(monkeypatch: pytest.MonkeyPatch) -> None:
    params = _captured_update_params(monkeypatch, filters={"slug": "neq.x", "id": "is.null"})
    assert params == {"slug": "eq.neq.x", "id": "eq.is.null"}


def test_null_columns_is_the_only_way_to_narrow_an_update(monkeypatch: pytest.MonkeyPatch) -> None:
    params = _captured_update_params(
        monkeypatch, filters={"user_id": "u1"}, kwargs={"null_columns": ("org_id",)}
    )
    assert params == {"user_id": "eq.u1", "org_id": "is.null"}
