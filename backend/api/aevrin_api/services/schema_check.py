"""Does the database this build is talking to have the columns it writes?

This exists because of a specific outage. A deploy shipped an API that writes
`scans.server_command` and four other new fields against a database where the
migration adding them had not been applied. PostgREST refused every one of
those writes, the refusals were swallowed, and scans ran to completion and
were never recorded as finished - a spinner with no end, for six hours, with a
healthy container and a green deploy.

`test_schema_projections.py` cannot catch that. It compares the code against
the migration *files*, and the file existed; what differed was the database.
Only something that asks the running database can see this.

So it is wired into `/health`, which is what the container's HEALTHCHECK polls
and what `remote-deploy.sh` waits on before it stops rolling back. An image
whose schema expectations are not met never becomes healthy, and the deploy
reverts to the previous one on its own. A broken deploy that rolls back beats
a green deploy that silently loses every scan.

Keep `REQUIRED_COLUMNS` to fields the code genuinely cannot work without. It
is a deploy gate: a name listed here in error takes the site down.
"""

from __future__ import annotations

import logging

from aevrin_api.db import SupabaseRest

logger = logging.getLogger("aevrin.schema")

# Columns this build writes or reads on paths that decide whether a scan is
# recorded at all. Added by migration 0047; without them a scan cannot be
# marked finished.
REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "scans": ("server_command", "scanner_name", "scanner_version", "invocation_channel"),
}


async def missing_columns(db: SupabaseRest) -> list[str]:
    """`table.column` entries this database does not have.

    A transient failure is deliberately *not* drift. PostgREST answers a
    request for an unknown column with a definite error, and that is the only
    thing treated as missing here - reporting a network blip as a schema
    problem would fail an otherwise fine deploy and send whoever is on call
    looking for a migration that was never the issue.
    """
    missing: list[str] = []
    for table, columns in REQUIRED_COLUMNS.items():
        try:
            await db.select(table, {}, columns=",".join(columns), limit=1)
        except Exception as exc:  # noqa: BLE001 - the message is the signal
            text = str(exc).lower()
            if "does not exist" in text or "42703" in text or "unknown column" in text:
                missing.extend(f"{table}.{c}" for c in columns)
                logger.error(
                    "schema drift: %s is missing one of %s - migrations are behind this build",
                    table,
                    ", ".join(columns),
                )
            else:
                logger.warning("schema check on %s was inconclusive: %s", table, exc)
    return missing


class SchemaStatus:
    """Remembers a healthy answer; keeps re-asking an unhealthy one.

    The asymmetry is the point. A schema that satisfies this build cannot stop
    doing so while the process runs, so that result is cached and `/health`
    stays cheap. Drift, on the other hand, is fixed by applying a migration to
    a database this process does not own - so it is re-checked every time, and
    the API recovers on its own once the migration lands, with no restart.
    """

    def __init__(self) -> None:
        self._ok = False

    async def missing(self, db: SupabaseRest) -> list[str]:
        if self._ok:
            return []
        found = await missing_columns(db)
        if not found:
            self._ok = True
        return found
