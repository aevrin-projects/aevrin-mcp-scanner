"""POST /ai/explain, through the HTTP layer.

The route declared its body as `body: Any`, which FastAPI reads as a
required *query* parameter: every explain request was refused with 422
before any code ran, and the button showed "AI explanation unavailable
right now" to every user with a working key. The tests that existed called
the route function with a dict, past the layer that was broken, so these
post real JSON through the app.
"""

from __future__ import annotations

from typing import Any

import pytest
from starlette.testclient import TestClient

from aevrin_api.controllers import ai_controller
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.main import app
from aevrin_api.routes.deps import get_current_user, get_db

USER = "00000000-0000-0000-0000-0000000000aa"


class _NoRows:
    async def select(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(USER, None)
    app.dependency_overrides[get_db] = lambda: _NoRows()
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def test_a_json_body_reaches_the_controller(client, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    async def explain_subject(db: Any, settings: Any, *, user_id: str, body: Any) -> dict[str, Any]:
        seen.update(user_id=user_id, subject_type=body.subject_type, detailed=body.detailed)
        return {"available": False, "reason": "No AI provider is configured."}

    monkeypatch.setattr(ai_controller, "explain_subject", explain_subject)
    response = client.post(
        "/ai/explain",
        json={"subject_type": "finding", "subject_id": "11111111-1111-1111-1111-111111111111", "detailed": True},
    )

    assert response.status_code == 200, response.text
    assert seen == {"user_id": USER, "subject_type": "finding", "detailed": True}


def test_a_malformed_subject_id_is_not_found_not_a_server_error(client) -> None:
    response = client.post("/ai/explain", json={"subject_type": "scan", "subject_id": "not-an-id"})
    assert response.status_code == 404


def test_a_subject_the_caller_cannot_read_is_not_found(client) -> None:
    response = client.post(
        "/ai/explain", json={"subject_type": "finding", "subject_id": "11111111-1111-1111-1111-111111111111"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Nothing found to explain."


def test_an_unknown_subject_type_is_refused_as_invalid(client) -> None:
    response = client.post("/ai/explain", json={"subject_type": "listing", "subject_id": "x"})
    assert response.status_code == 422
