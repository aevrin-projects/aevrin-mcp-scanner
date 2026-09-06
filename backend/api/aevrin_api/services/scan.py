"""Glues backend/scanner-core's pipeline to persistence and DefectDojo.

The pipeline itself is synchronous (subprocess/docker calls) and takes
60-90+ seconds, so it runs in a worker thread via `asyncio.to_thread` rather
than blocking the event loop. Stage/finding callbacks fire from that thread
and write straight to Supabase with a plain sync httpx client, bridging
back into the async event loop for a handful of simple POSTs would add
complexity for no real benefit here.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from aevrin_scanner_core import (
    Finding,
    InvocationChannel,
    Scan,
    ScanStage,
    TargetType,
)
from aevrin_scanner_core.pipeline import PipelineConfig, run_pipeline

from aevrin_api.config import Settings
from aevrin_api.integrations.defectdojo_client import DefectDojoClient, DefectDojoUnavailable
from aevrin_api.services.triage import triage_findings

logger = logging.getLogger("aevrin.scan_service")

# A single source scan can briefly consume multiple gigabytes while Semgrep,
# Trivy, and the Go-based secret scanners initialize. This API runs in
# one container, so overlapping BackgroundTasks compete for the same cgroup
# and make otherwise healthy tools exit immediately. Keep requests queued at
# the application boundary and run one scan pipeline per API instance.
_SCAN_SLOT = asyncio.Semaphore(1)


class WriteRejected(RuntimeError):
    """A database write that decides a scan's outcome was refused.

    These used to be logged at warning level and swallowed, which is how a
    scan could run to completion and then sit at `running` forever: the
    terminal status write was rejected (a column the deployed schema did not
    have yet), nothing raised, and the row was simply never finished. A user
    watching that scan sees a spinner with no end and no error.

    Writes that only enrich a result - the hook cache, DefectDojo - stay
    best-effort. Writes that determine whether a scan is finished, and what it
    found, do not.
    """


class _SyncRest:
    """Minimal sync PostgREST client for use inside the pipeline's worker
    thread, intentionally separate from db.SupabaseRest (async), which
    can't be safely called from a non-event-loop thread."""

    def __init__(self, settings: Settings):
        self._base_url = f"{settings.supabase_url}/rest/v1"
        self._headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation,resolution=merge-duplicates",
        }

    def upsert(
        self,
        table: str,
        rows: dict[str, Any] | list[dict[str, Any]],
        on_conflict: str,
        *,
        required: bool = False,
    ) -> None:
        try:
            httpx.post(
                f"{self._base_url}/{table}",
                headers=self._headers,
                json=rows,
                params={"on_conflict": on_conflict},
                timeout=10,
            ).raise_for_status()
        except httpx.HTTPError as exc:
            if required:
                raise WriteRejected(f"upsert into {table} failed: {exc}") from exc
            logger.warning("scan_service: upsert into %s failed: %s", table, exc)

    def patch(
        self,
        table: str,
        filters: dict[str, str],
        patch: dict[str, Any],
        *,
        required: bool = False,
    ) -> None:
        try:
            httpx.patch(
                f"{self._base_url}/{table}",
                headers=self._headers,
                json=patch,
                params={k: f"eq.{v}" for k, v in filters.items()},
                timeout=10,
            ).raise_for_status()
        except httpx.HTTPError as exc:
            if required:
                raise WriteRejected(f"patch on {table} failed: {exc}") from exc
            logger.warning("scan_service: patch on %s failed: %s", table, exc)

    def get(self, table: str, filters: dict[str, str]) -> list[dict[str, Any]]:
        resp = httpx.get(
            f"{self._base_url}/{table}",
            headers=self._headers,
            params={**{k: f"eq.{v}" for k, v in filters.items()}, "select": "*"},
            timeout=10,
        )
        resp.raise_for_status()
        result: list[dict[str, Any]] = resp.json()
        return result

    def delete_ids_not_in(self, table: str, scan_id: str, keep_ids: list[str]) -> None:
        """Removes rows orphaned by postprocessing (cross-scanner dedup and
        root-cause grouping can collapse several streamed findings into one;
        see _resync_postprocessed_findings): everything for this scan_id
        NOT in the final surviving id set. A scan with zero surviving
        findings still needs every earlier row cleared, so this runs even
        when keep_ids is empty (PostgREST's not.in.() with no values matches
        everything, same as no filter at all)."""
        id_list = ",".join(keep_ids) if keep_ids else "00000000-0000-0000-0000-000000000000"
        try:
            httpx.delete(
                f"{self._base_url}/{table}",
                headers=self._headers,
                params={"scan_id": f"eq.{scan_id}", "id": f"not.in.({id_list})"},
                timeout=10,
            ).raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("scan_service: delete_ids_not_in on %s failed: %s", table, exc)


def _finding_row(f: Finding, user_id: str) -> dict[str, Any]:
    return {
        "id": str(f.id),
        "scan_id": str(f.scan_id),
        "user_id": user_id,
        "tool": f.tool.value,
        "owasp_category": f.owasp_category.value,
        "severity": f.severity.value,
        "title": f.title,
        "description": f.description,
        "file_path": f.location.file_path,
        "line_start": f.location.line_start,
        "line_end": f.location.line_end,
        "manifest_field": f.location.manifest_field,
        "tool_name_in_manifest": f.location.tool_name_in_manifest,
        "remediation": f.remediation,
        "raw": f.raw,
        "triage_status": f.triage_status.value,
        "occurrence_count": f.occurrence_count,
        "additional_locations": [loc.model_dump(mode="json") for loc in f.additional_locations],
    }


def _stage_row(stage: ScanStage) -> dict[str, object]:
    return {
        "scan_id": str(stage.scan_id),
        "name": stage.name.value,
        "status": stage.status.value,
        "error": stage.error,
        "started_at": stage.started_at.isoformat() if stage.started_at else None,
        "finished_at": stage.finished_at.isoformat() if stage.finished_at else None,
    }


# Statuses that mean "a worker is still expected to touch this row".
_OPEN_STATUSES = {"queued", "running"}


def _mark_scan_failed(rest: _SyncRest, scan_id: UUID, user_id: str) -> None:
    rest.patch(
        "scans",
        {"id": str(scan_id), "user_id": user_id},
        {
            "status": "failed",
            "risk_score": None,
            "grade": None,
            "error": (
                "The scan worker could not finalize this scan. Retry once; "
                "if it repeats, review the failed stage or contact support."
            ),
            "completed_at": datetime.now(UTC).isoformat(),
        },
    )


def _ensure_terminal(rest: _SyncRest, scan_id: UUID, user_id: str) -> None:
    """Leave no scan claiming to be in progress once its worker has stopped.

    A scan row is only ever advanced by the worker that owns it, so once that
    worker is done the row must be in a terminal state. If it is not, the
    write that should have finished it did not land, and the honest rendering
    of that is `failed` - not a spinner that never resolves.
    """
    try:
        rows = rest.get("scans", {"id": str(scan_id), "user_id": user_id})
    except httpx.HTTPError:
        logger.exception("scan_service: could not confirm final state of scan %s", scan_id)
        return
    if not rows:
        return
    if str(rows[0].get("status")) in _OPEN_STATUSES:
        logger.error(
            "scan_service: scan %s left open by its worker; forcing failed", scan_id
        )
        _mark_scan_failed(rest, scan_id, user_id)


def _persist_completed_scan(
    rest: _SyncRest,
    scan: Scan,
    user_id: str,
    durable_target: str,
) -> None:
    """Writes the finished scan and the hook cache."""
    completed_at = scan.completed_at.isoformat() if scan.completed_at else None
    rest.patch(
        "scans",
        {"id": str(scan.id), "user_id": user_id},
        {
            "status": scan.status.value,
            "mcp_tools_declared": scan.mcp_tools_declared,
            "risk_score": scan.risk_score,
            "grade": scan.grade,
            "mcp_detected": scan.mcp_detected,
            # Recorded for reproducibility (§20). `server_command` is the one
            # that matters most: a grade attributed to the wrong package is the
            # failure mode that resolution exists to prevent, and this is where
            # it becomes visible after the fact.
            "server_command": scan.server_command,
            "scanner_name": scan.scanner_name,
            "scanner_version": scan.scanner_version,
            "invocation_channel": (
                scan.invocation_channel.value if scan.invocation_channel else None
            ),
            "unreliable_stages": [s.value for s in scan.unreliable_stages],
            "completed_at": completed_at,
        },
        # The write that ends the scan. If it is refused the scan is not
        # finished, whatever the pipeline produced, and saying so beats
        # leaving a row that claims to still be working.
        required=True,
    )

    rest.upsert(
        "hook_cache",
        {
            "user_id": user_id,
            "target": durable_target,
            "last_scan_id": str(scan.id),
            "last_risk_score": scan.risk_score,
            "last_grade": scan.grade,
            "last_status": scan.status.value,
            "checked_at": completed_at,
        },
        on_conflict="user_id,target",
    )


def _run_and_persist(
    scan_id: UUID,
    user_id: str,
    target_type: TargetType,
    target: str,
    settings: Settings,
    stored_target: str | None = None,
    channel: InvocationChannel = InvocationChannel.DASHBOARD,
    server_command: str | None = None,
) -> None:
    durable_target = stored_target or target
    rest = _SyncRest(settings)
    rest.patch(
        "scans",
        {"id": str(scan_id), "user_id": user_id},
        {"status": "running", "error": None},
    )

    def on_stage(stage: ScanStage) -> None:
        rest.upsert("scan_stages", _stage_row(stage), on_conflict="scan_id,name")

    def on_findings(findings: list[Finding]) -> None:
        rest.upsert("findings", [_finding_row(f, user_id) for f in findings], on_conflict="id")

    try:
        # The channel is passed through rather than defaulted here: every
        # scan used to record "dashboard" whatever started it, which made the
        # column worse than absent - a marketplace or CLI-triggered scan was
        # labelled as something a user did in the browser. It never changes
        # the result; it only says who asked.
        config = PipelineConfig(
            github_token=settings.github_token,
            invocation_channel=channel,
            server_command=server_command,
        )

        scan = run_pipeline(
            target_type=target_type,
            target=target,
            config=config,
            on_stage=on_stage,
            on_findings=on_findings,
            scan_id=scan_id,
        )
    except Exception:
        logger.exception("scan_service: scan %s failed before aggregation", scan_id)
        _mark_scan_failed(rest, scan_id, user_id)
        return

    try:
        _persist_completed_scan(rest, scan, user_id, durable_target)
    except Exception:
        # Previously outside the try entirely, so a rejected terminal write
        # escaped the worker thread and left the row at `running` with nothing
        # to explain it.
        logger.exception("scan_service: scan %s could not be persisted", scan_id)
        _mark_scan_failed(rest, scan_id, user_id)
        return
    finally:
        # Verified, not assumed. Everything above can fail in a way that never
        # reaches an except block - a swallowed write, a thread killed
        # mid-flight - and the symptom is always the same: a scan that runs
        # forever. This reads the row back and forces a terminal state if it
        # is still open.
        _ensure_terminal(rest, scan_id, user_id)

    _push_to_defectdojo_best_effort(settings, durable_target, scan.id, scan.findings)
    _run_triage_best_effort(rest, settings, user_id, scan.findings, scan.id)


def _run_triage_best_effort(
    rest: _SyncRest, settings: Settings, user_id: str, findings: list[Finding], scan_id_for_triage: UUID | None = None
) -> None:
    """LLM triage (addendum §2): runs on every tier now, and never allowed to
    affect the deterministic result stored above: this only *adds* llm_*
    columns onto findings that already exist, after the fact. Isolated the
    same way DefectDojo is (own try/except, own event loop) so a triage
    outage can never take down a scan."""
    accounts = rest.get("accounts", {"user_id": user_id})
    if not accounts:
        return
    account = accounts[0]

    async def _triage() -> None:
        try:
            results, note = await triage_findings(settings, account, findings)
        except Exception:
            logger.exception("scan_service: triage failed for user %s", user_id)
            return
        if note:
            rest.patch("scans", {"id": str(scan_id_for_triage)}, {"triage_note": note})
        triaged_at = datetime.now(UTC).isoformat()
        for result in results:
            rest.patch(
                "findings",
                {"id": result.finding_id, "user_id": user_id},
                {
                    "llm_classification": result.classification,
                    "llm_severity": result.severity,
                    "llm_reasoning": result.reasoning,
                    "llm_remediation": result.remediation,
                    "llm_model": result.model,
                    "llm_triaged_at": triaged_at,
                },
            )

    asyncio.run(_triage())


def _push_to_defectdojo_best_effort(settings: Settings, target: str, scan_id: UUID, findings: list[Finding]) -> None:
    """DefectDojo is for aggregation/dedupe/compliance reporting on top of
    results we already own; an outage here must never take down the scan
    itself, which is why this is isolated and swallows its own errors."""
    try:
        client = DefectDojoClient(settings)
    except DefectDojoUnavailable:
        logger.info("scan_service: DefectDojo not configured, skipping push for scan %s", scan_id)
        return

    async def _push() -> None:
        try:
            product_id = await client.get_or_create_product(target)
            engagement_id = await client.get_or_create_engagement(product_id, str(scan_id))
            test_id = await client.create_test(engagement_id, str(scan_id))
            for finding in findings:
                await client.push_finding(test_id, target, finding)
        except Exception:
            logger.exception("scan_service: DefectDojo push failed for scan %s", scan_id)

    asyncio.run(_push())


async def start_scan(
    scan_id: UUID,
    user_id: str,
    target_type: TargetType,
    target: str,
    settings: Settings,
    stored_target: str | None = None,
    channel: InvocationChannel = InvocationChannel.DASHBOARD,
    server_command: str | None = None,
) -> None:
    """Entry point called from the request handler via BackgroundTasks;
    waits for bounded worker capacity, then runs the blocking pipeline off the
    event loop. The database row deliberately remains `queued` while waiting.

    `channel` records which surface asked - dashboard, marketplace, CLI - and
    `server_command` lets a caller that already knows how to start the server
    skip resolution. Neither affects the security result: the same server
    scanned from two surfaces produces the same findings and the same grade.
    """
    async with _SCAN_SLOT:
        await asyncio.to_thread(
            _run_and_persist,
            scan_id,
            user_id,
            target_type,
            target,
            settings,
            stored_target,
            channel,
            server_command,
        )
