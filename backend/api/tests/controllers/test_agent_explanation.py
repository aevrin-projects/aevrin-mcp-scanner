"""Explaining an agent's posture with AI.

The evidence is read through the same path as the agent page, so what the
model is told is exactly what the page shows, and a caller can never have an
agent explained that the page would not show them: the explanation would
otherwise be a way to read another account's configuration.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import pytest
from starlette.testclient import TestClient

from aevrin_api.controllers import ai_controller
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.main import app
from aevrin_api.routes.deps import get_current_user, get_db
from aevrin_api.services.ai import explain

from .test_agent_tenant_isolation import MINE, THEIR_ROW, StrictDb, snapshot_row


def _evidence(db: StrictDb, agent_id: str) -> dict[str, Any] | None:
    return asyncio.run(
        ai_controller._gather_evidence(
            db, user_id=MINE, subject_type="agent_posture", subject_id=agent_id
        )
    )


def test_another_accounts_agent_cannot_be_explained() -> None:
    with pytest.raises(PermissionError):
        _evidence(StrictDb([THEIR_ROW]), THEIR_ROW["id"])


def test_the_evidence_is_the_score_and_the_rules_behind_it() -> None:
    row = snapshot_row(MINE, "MY-BOX")
    row["snapshot"]["capabilities"] = [
        {
            "capability": "shell",
            "level": "full",
            "evidence": [
                {"detail": "permissions.allow: Bash", "source_path": "/home/ana/.claude/settings.json", "scope": "user"}
            ],
        }
    ]
    row["snapshot"]["credentials"] = [
        {"kind": "github_token", "present": True, "source": "environment", "location": "GITHUB_TOKEN"}
    ]
    document = _evidence(StrictDb([row]), row["id"])
    assert document is not None

    # The deductions add up to the score the page shows, so "why this score"
    # is answered from the real arithmetic rather than a guess.
    score = int(document["context"]["posture_score"].split("/")[0])
    assert 100 - sum(f["points"] for f in document["posture_factors"]) == score
    assert document["context"]["risk_level"] == "critical"

    # The rule that granted the access travels with it, so the answer can
    # name what to change.
    shell = next(c for c in document["agent_capabilities"] if c["capability"] == "shell")
    assert shell["level"] == "full"
    assert shell["granted_by"] == ["permissions.allow: Bash"]
    assert {"rule": "Bash", "effect": "allow", "scope": "user"} in document["permission_rules"]

    # Paths name people (a home directory) and are not needed to explain a
    # rule; credential locations are metadata the model has no use for.
    rendered = json.dumps(document)
    assert "/home/ana" not in rendered
    assert "GITHUB_TOKEN" not in rendered


class _NoRows:
    async def select(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []


def test_the_route_answers_not_found_for_an_agent_the_caller_cannot_read() -> None:
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(MINE, None)
    app.dependency_overrides[get_db] = lambda: _NoRows()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/ai/explain", json={"subject_type": "agent_posture", "subject_id": str(uuid4())}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found."


def test_a_changed_prompt_does_not_serve_answers_cached_under_the_old_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    looked_up: list[str] = []

    async def get_cached(db: Any, *, hash_value: str, subject_type: str) -> dict[str, Any]:
        looked_up.append(hash_value)
        return {"summary": "cached"}

    monkeypatch.setattr(explain, "get_cached", get_cached)
    document = {"subject_type": "agent_posture", "context": {"risk_level": "high"}}
    for version in ("old", "new"):
        monkeypatch.setattr(explain, "PROMPT_VERSION", version)
        asyncio.run(
            explain.explain(None, None, user_id=MINE, document=document, subject_type="agent_posture")  # type: ignore[arg-type]
        )
    assert looked_up[0] != looked_up[1]
