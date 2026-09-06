"""The check that would have turned a six-hour outage into a rolled-back deploy.

An API was deployed that writes `scans.server_command` and four other columns
against a database where the migration adding them had not been applied.
PostgREST refused the writes, the refusals were swallowed, and every scan ran
to completion and was never recorded as finished. The container was healthy
and the deploy was green the whole time.

`test_schema_projections.py` could not see it: that test compares the code to
the migration *files*, and the file existed. Only asking the running database
distinguishes "the migration is written" from "the migration is applied".
"""

from __future__ import annotations

import asyncio
from typing import Any

from aevrin_api.services.schema_check import REQUIRED_COLUMNS, SchemaStatus, missing_columns


class _Db:
    """PostgREST's behaviour for the two cases that matter."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    async def select(self, table: str, filters: dict[str, str], **kwargs: Any) -> list[Any]:
        self.calls += 1
        if self.error:
            raise self.error
        return []


def test_a_database_with_the_columns_reports_no_drift() -> None:
    assert asyncio.run(missing_columns(_Db())) == []  # type: ignore[arg-type]


def test_a_missing_column_is_reported_with_its_table() -> None:
    """The exact shape of the outage: the migration exists in the repository
    and has not been applied to this database."""
    db = _Db(RuntimeError('column scans.server_command does not exist'))
    missing = asyncio.run(missing_columns(db))  # type: ignore[arg-type]

    assert missing, "drift must be detected"
    assert all(entry.startswith("scans.") for entry in missing)
    assert "scans.server_command" in missing


def test_an_unrelated_failure_is_not_reported_as_drift() -> None:
    """This gates deploys. A network blip reported as a schema problem fails
    an otherwise fine rollout and sends someone hunting a migration that was
    never the issue."""
    db = _Db(TimeoutError("connection reset by peer"))
    assert asyncio.run(missing_columns(db)) == []  # type: ignore[arg-type]


def test_a_healthy_answer_is_cached_and_a_broken_one_is_not() -> None:
    """The asymmetry is deliberate.

    A schema that satisfies this build cannot stop doing so while the process
    runs, so that answer is remembered and /health stays cheap. Drift is fixed
    by applying a migration to a database this process does not own, so it is
    re-asked every time and the API recovers by itself once the migration
    lands - without needing a restart nobody would think to perform.
    """
    healthy = _Db()
    status_ok = SchemaStatus()
    asyncio.run(status_ok.missing(healthy))  # type: ignore[arg-type]
    asyncio.run(status_ok.missing(healthy))  # type: ignore[arg-type]
    assert healthy.calls == 1, "a healthy schema is only probed once"

    broken = _Db(RuntimeError("column scans.scanner_name does not exist"))
    status_bad = SchemaStatus()
    assert asyncio.run(status_bad.missing(broken))  # type: ignore[arg-type]
    assert asyncio.run(status_bad.missing(broken))  # type: ignore[arg-type]
    assert broken.calls == 2, "drift must be re-checked so it can clear itself"


def test_the_required_columns_are_the_ones_migration_0047_adds() -> None:
    """Pinned deliberately. This list gates every deploy: a name added here in
    error takes the site down, and one removed lets the outage recur."""
    assert REQUIRED_COLUMNS["scans"] == (
        "server_command",
        "scanner_name",
        "scanner_version",
        "invocation_channel",
    )
