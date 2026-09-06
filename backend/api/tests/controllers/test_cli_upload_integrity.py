"""What /cli/upload can and cannot promise about a client-reported grade.

This file used to assert that the API recomputed the grade from the uploaded
findings, so a modified CLI could not publish a flattering letter. That check
is gone, and its absence is a deliberate trade-off: scoring belongs to the
engine, which derives a grade by launching the server and reading its tools.
Re-deriving a letter from finding rows would mean a second scoring algorithm,
and two graders end up disagreeing about one server.

Two refusals survive, and both compare the client's claims against the
client's own evidence rather than recomputing anything: a grade with no
enumerated tools, and an ALLOW-band letter beside a Critical or High finding.

Read `test_the_endpoint_refuses_a_grade_with_no_tools` before adding anything
here. The first of those guards was deleted from the controller and nothing
noticed, because the tests covering it called `grade_scan` directly instead of
the endpoint - the library kept behaving correctly while the endpoint stopped
enforcing anything. Assertions about what an upload is allowed to persist
belong against `upload_scan`, not against the library it calls.

The protection that was genuinely lost - detecting a client that under-reports
its own findings consistently - is named here so it is not quietly forgotten.
Catching that needs a real rescan or a signed attestation; neither exists.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from aevrin_scanner_core import Grade, grade_scan
from fastapi import BackgroundTasks, HTTPException

from aevrin_api.controllers import cli_controller as cli
from aevrin_api.controllers.cli_controller import _to_core_finding
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.schemas import CliUploadFinding, CliUploadRequest, CliUploadStage


def _finding(severity: str) -> CliUploadFinding:
    return CliUploadFinding(
        id=uuid4(),
        tool="mcp-scanner",
        owasp_category="MCP05",
        severity=severity,
        title="Example finding",
        description="Example description",
        remediation="Fix it",
    )


def _regrade(findings, scan_id, tools_declared: int = 3, risk=27, grade="C"):
    """How the API presents a stored verdict: it is handed the engine's
    numbers and chooses wording and policy, never a score of its own."""
    return grade_scan(
        [_to_core_finding(f, scan_id) for f in findings],
        engine_risk_score=risk,
        engine_grade=Grade(grade) if grade else None,
        coverage_complete=True,
        tools_discovered=tools_declared,
    )


def test_the_engine_verdict_is_presented_not_recomputed():
    """One informational finding alongside a C/27 verdict must still read as
    C/27. The finding list does not out-vote the engine."""
    scan_id = uuid4()
    result = _regrade([_finding("info")], scan_id, risk=27, grade="C")
    assert result.risk_score == 27
    assert result.grade is not None and result.grade.value == "C"


def test_a_grade_is_withheld_when_no_tools_were_enumerated():
    """The floor that survives. A modified CLI reporting an A for a target
    whose tools it never read gets no letter, whatever it submitted."""
    scan_id = uuid4()
    result = _regrade([_finding("info")], scan_id, tools_declared=0, risk=0, grade="A")
    assert result.grade is None
    assert result.incomplete is True


def test_to_core_finding_round_trips_location_fields():
    scan_id = uuid4()
    f = CliUploadFinding(
        id=uuid4(),
        tool="mcp-scanner",
        owasp_category="MCP01",
        severity="high",
        title="t",
        description="d",
        file_path="app.py",
        line_start=10,
        line_end=12,
        remediation="r",
    )
    core = _to_core_finding(f, scan_id)
    assert core.scan_id == scan_id
    assert core.location.file_path == "app.py"
    assert core.location.line_start == 10
    assert core.location.line_end == 12


class _UploadDb:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "scans": [],
            "scan_stages": [],
            "findings": [],
            "hook_cache": [],
        }

    async def select(self, table: str, filters: dict[str, str]) -> list[dict[str, Any]]:
        return [
            row
            for row in self.tables[table]
            if all(str(row.get(key)) == value for key, value in filters.items())
        ]

    async def insert(
        self,
        table: str,
        rows: dict[str, Any] | list[dict[str, Any]],
        *,
        upsert_on: str | None = None,
    ) -> list[dict[str, Any]]:
        incoming = rows if isinstance(rows, list) else [rows]
        if upsert_on:
            conflict_keys = upsert_on.split(",")
            for row in incoming:
                existing = next(
                    (
                        item
                        for item in self.tables[table]
                        if all(item.get(key) == row.get(key) for key in conflict_keys)
                    ),
                    None,
                )
                if existing:
                    existing.update(row)
                else:
                    self.tables[table].append(dict(row))
        else:
            self.tables[table].extend(dict(row) for row in incoming)
        return [dict(row) for row in incoming]

    async def update(
        self, table: str, filters: dict[str, str], patch: dict[str, Any]
    ) -> list[dict[str, Any]]:
        rows = await self.select(table, filters)
        for row in rows:
            row.update(patch)
        return rows


def test_cli_upload_is_idempotent_and_preserves_full_dashboard_record(monkeypatch, settings):
    scan_id = uuid4()
    finding = _finding("critical")
    started = datetime.now(UTC) - timedelta(seconds=68)
    completed = datetime.now(UTC)
    request = CliUploadRequest(
        scan_id=scan_id,
        target_type="local_path",
        target="/workspace/example-server",
        risk_score=60,
        grade="D",
        status="completed",
        created_at=started,
        completed_at=completed,
        mcp_detected=True,
        mcp_tools_declared=["search"],
        stages=[
            CliUploadStage(
                name="analyzing",
                status="done",
                started_at=started,
                finished_at=completed,
            )
        ],
        findings=[finding],
    )
    db = _UploadDb()
    user = AuthenticatedUser("user-1", "developer@example.com")
    quota_calls = 0

    async def fake_quota(*args: Any, **kwargs: Any) -> None:
        nonlocal quota_calls
        quota_calls += 1

    monkeypatch.setattr(cli, "enforce_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "check_and_increment_quota", fake_quota)

    first = asyncio.run(cli.upload_scan(request, BackgroundTasks(), user.id, db, settings))  # type: ignore[arg-type]
    second = asyncio.run(cli.upload_scan(request, BackgroundTasks(), user.id, db, settings))  # type: ignore[arg-type]

    assert first.id == second.id == scan_id
    assert quota_calls == 1
    assert len(db.tables["scans"]) == 1
    assert db.tables["scans"][0]["source"] == "cli"
    assert db.tables["scans"][0]["created_at"] == started.isoformat()
    assert db.tables["scans"][0]["completed_at"] == completed.isoformat()
    # The tools the server actually returned survive the upload; they are what
    # a grade is a claim about, so an upload that loses them loses the grade.
    assert db.tables["scans"][0]["mcp_tools_declared"] == ["search"]
    assert len(db.tables["scan_stages"]) == 1
    assert len(db.tables["findings"]) == 1
    assert db.tables["findings"][0]["id"] == str(finding.id)


@pytest.mark.parametrize(
    ("persisted_source", "persisted_target"),
    [("dashboard", "/workspace/example-server"), ("cli", "/workspace/other-server")],
)
def test_cli_upload_cannot_overwrite_an_unrelated_scan(
    monkeypatch, settings, persisted_source: str, persisted_target: str
):
    scan_id = uuid4()
    db = _UploadDb()
    db.tables["scans"].append(
        {
            "id": str(scan_id),
            "user_id": "user-1",
            "source": persisted_source,
            "target_type": "local_path",
            "target": persisted_target,
        }
    )
    # A coherent payload on purpose: this test is about ID ownership, and a
    # self-contradictory grade would be refused as malformed before the
    # conflict check ever ran, making the assertion below pass for the wrong
    # reason.
    request = CliUploadRequest(
        scan_id=scan_id,
        target_type="local_path",
        target="/workspace/example-server",
        risk_score=0,
        grade="A",
        status="completed",
        mcp_tools_declared=["search"],
        findings=[],
    )
    monkeypatch.setattr(cli, "enforce_rate_limit", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            cli.upload_scan(
                request,
                BackgroundTasks(),
                "user-1",
                db,  # type: ignore[arg-type]
                settings,
            )
        )

    assert exc_info.value.status_code == 409


def _upload(monkeypatch, settings, db: _UploadDb, **overrides: Any):
    """Drive the real endpoint, not the grading library.

    Every assertion below goes through `upload_scan` deliberately. The
    library-level tests at the top of this file kept passing while the
    endpoint's own guard had been deleted, because they never call it - see
    `test_the_endpoint_refuses_a_grade_with_no_tools`.
    """
    monkeypatch.setattr(cli, "enforce_rate_limit", lambda *a, **k: None)

    async def fake_quota(*a: Any, **k: Any) -> None:
        return None

    monkeypatch.setattr(cli, "check_and_increment_quota", fake_quota)
    fields: dict[str, Any] = {
        "target_type": "local_path",
        "target": "/workspace/example-server",
        "status": "completed",
        "findings": [_finding("info")],
    }
    fields.update(overrides)
    body = CliUploadRequest(**fields)
    return asyncio.run(cli.upload_scan(body, BackgroundTasks(), "user-1", db, settings))  # type: ignore[arg-type]


def test_the_endpoint_refuses_a_grade_with_no_tools(monkeypatch, settings):
    """The floor, asserted where it actually lives.

    This existed only as a claim in a comment: the `if` guarding it had been
    deleted, leaving its body attached to the `except` above it (dead code
    after a `raise`) and the `else` silently rebound to the `try`. The module
    still parsed, mypy still passed, and the library-level test above still
    went green - so an upload could claim any letter for a target whose tools
    it never read. Only a test that calls the endpoint can see this.
    """
    db = _UploadDb()
    with pytest.raises(HTTPException) as excinfo:
        _upload(monkeypatch, settings, db, grade="A", risk_score=0, mcp_tools_declared=[])
    assert excinfo.value.status_code == 422
    assert not db.tables["scans"], "nothing may be persisted for a refused upload"


def test_the_endpoint_refuses_an_allow_grade_beside_a_critical_finding(monkeypatch, settings):
    """A tampered CLI's cheapest win: claim A so the hook stops prompting,
    while the payload's own evidence says Critical. No scoring is needed to
    know those cannot both be true."""
    db = _UploadDb()
    with pytest.raises(HTTPException) as excinfo:
        _upload(
            monkeypatch, settings, db,
            grade="A", risk_score=0,
            mcp_tools_declared=["search"],
            findings=[_finding("critical")],
        )
    assert excinfo.value.status_code == 422
    assert "critical" in str(excinfo.value.detail).lower()
    assert not db.tables["scans"]


def test_an_honest_upload_still_stores_the_engine_verdict_unchanged(monkeypatch, settings):
    """The check must refuse contradictions without touching real results: a
    Critical finding reported as D is coherent, and D/60 is what gets stored."""
    db = _UploadDb()
    result = _upload(
        monkeypatch, settings, db,
        grade="D", risk_score=60,
        mcp_tools_declared=["search"],
        findings=[_finding("critical")],
    )
    assert result.grade == "D"
    assert db.tables["scans"][0]["grade"] == "D"
    assert db.tables["scans"][0]["risk_score"] == 60


def test_an_ungraded_incomplete_upload_is_still_accepted(monkeypatch, settings):
    """An incomplete scan reports no tools *and* no grade. That is the honest
    shape of a failed scan and must not be caught by the guard above."""
    db = _UploadDb()
    result = _upload(
        monkeypatch, settings, db,
        grade=None, risk_score=None, status="incomplete", mcp_tools_declared=[],
    )
    assert result.grade is None
    assert db.tables["scans"][0]["grade"] is None
