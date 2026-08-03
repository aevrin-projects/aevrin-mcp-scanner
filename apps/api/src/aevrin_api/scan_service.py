"""Glues packages/scanner-core's pipeline to persistence and DefectDojo.

The pipeline itself is synchronous (subprocess/docker calls) and takes
60-90+ seconds, so it runs in a worker thread via `asyncio.to_thread` rather
than blocking the event loop. Stage/finding callbacks fire from that thread
and write straight to Supabase with a plain sync httpx client — bridging
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
from aevrin_scanner_core import Finding, ScanStage, TargetType
from aevrin_scanner_core.pipeline import PipelineConfig, run_pipeline

from .config import Settings
from .defectdojo_client import DefectDojoClient, DefectDojoUnavailable

logger = logging.getLogger("aevrin.scan_service")

# A single source scan can briefly consume multiple gigabytes while Semgrep,
# Trivy, and the Go-based secret scanners initialize. Railway runs this API in
# one container, so overlapping BackgroundTasks compete for the same cgroup
# and make otherwise healthy tools exit immediately. Keep requests queued at
# the application boundary and run one scan pipeline per API instance.
_SCAN_SLOT = asyncio.Semaphore(1)


class _SyncRest:
    """Minimal sync PostgREST client for use inside the pipeline's worker
    thread — intentionally separate from db.SupabaseRest (async), which
    can't be safely called from a non-event-loop thread."""

    def __init__(self, settings: Settings):
        self._base_url = f"{settings.supabase_url}/rest/v1"
        self._headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation,resolution=merge-duplicates",
        }

    def upsert(self, table: str, rows: dict[str, Any] | list[dict[str, Any]], on_conflict: str) -> None:
        try:
            httpx.post(
                f"{self._base_url}/{table}",
                headers=self._headers,
                json=rows,
                params={"on_conflict": on_conflict},
                timeout=10,
            ).raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("scan_service: upsert into %s failed: %s", table, exc)

    def patch(self, table: str, filters: dict[str, str], patch: dict[str, Any]) -> None:
        try:
            httpx.patch(
                f"{self._base_url}/{table}",
                headers=self._headers,
                json=patch,
                params={k: f"eq.{v}" for k, v in filters.items()},
                timeout=10,
            ).raise_for_status()
        except httpx.HTTPError as exc:
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
        "verified": f.verified,
        "not_tested": f.not_tested,
        "raw": f.raw,
        "triage_status": f.triage_status.value,
    }


def _run_and_persist(
    scan_id: UUID,
    user_id: str,
    target_type: TargetType,
    target: str,
    settings: Settings,
    stored_target: str | None = None,
) -> None:
    durable_target = stored_target or target
    rest = _SyncRest(settings)
    rest.patch(
        "scans",
        {"id": str(scan_id), "user_id": user_id},
        {"status": "running", "error": None},
    )

    def on_stage(stage: ScanStage) -> None:
        rest.upsert(
            "scan_stages",
            {
                "scan_id": str(stage.scan_id),
                "name": stage.name.value,
                "status": stage.status.value,
                "error": stage.error,
                "started_at": stage.started_at.isoformat() if stage.started_at else None,
                "finished_at": stage.finished_at.isoformat() if stage.finished_at else None,
            },
            on_conflict="scan_id,name",
        )

    def on_findings(findings: list[Finding]) -> None:
        rest.upsert("findings", [_finding_row(f, user_id) for f in findings], on_conflict="id")

    try:
        previous_rows = rest.get(
            "rug_pull_signatures", {"user_id": user_id, "target": durable_target}
        )
        previous_signatures = {
            row["server_name"]: row["signature_hash"] for row in previous_rows
        }
        config = PipelineConfig(
            github_token=settings.github_token,
            previous_signatures=previous_signatures,
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
        rest.patch(
            "scans",
            {"id": str(scan_id), "user_id": user_id},
            {
                "status": "failed",
                "score": None,
                "error": (
                    "The scan worker could not finalize this scan. Retry once; "
                    "if it repeats, review the failed stage or contact support."
                ),
                "completed_at": datetime.now(UTC).isoformat(),
            },
        )
        return

    rest.patch(
        "scans",
        {"id": str(scan.id), "user_id": user_id},
        {
            "status": scan.status.value,
            "score": scan.score,
            "mcp_detected": scan.mcp_detected,
            "unreliable_stages": [s.value for s in scan.unreliable_stages],
            "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
        },
    )

    if config.computed_signatures:
        rest.upsert(
            "rug_pull_signatures",
            [
                {
                    "user_id": user_id,
                    "target": durable_target,
                    "server_name": name,
                    "signature_hash": sig_hash,
                    "updated_at": scan.completed_at.isoformat() if scan.completed_at else None,
                }
                for name, sig_hash in config.computed_signatures
            ],
            on_conflict="user_id,target,server_name",
        )

    rest.upsert(
        "hook_cache",
        {
            "user_id": user_id,
            "target": durable_target,
            "last_scan_id": str(scan.id),
            "last_score": scan.score,
            "last_status": scan.status.value,
            "checked_at": scan.completed_at.isoformat() if scan.completed_at else None,
        },
        on_conflict="user_id,target",
    )

    _push_to_defectdojo_best_effort(settings, durable_target, scan.id, scan.findings)


def _push_to_defectdojo_best_effort(settings: Settings, target: str, scan_id: UUID, findings: list[Finding]) -> None:
    """DefectDojo is for aggregation/dedupe/compliance reporting on top of
    results we already own — an outage here must never take down the scan
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
                if finding.not_tested:
                    continue
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
) -> None:
    """Entry point called from the request handler via BackgroundTasks —
    waits for bounded worker capacity, then runs the blocking pipeline off the
    event loop. The database row deliberately remains `queued` while waiting."""
    async with _SCAN_SLOT:
        await asyncio.to_thread(
            _run_and_persist,
            scan_id,
            user_id,
            target_type,
            target,
            settings,
            stored_target,
        )
