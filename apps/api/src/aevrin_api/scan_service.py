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
from .triage import triage_findings

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

    def delete_ids_not_in(self, table: str, scan_id: str, keep_ids: list[str]) -> None:
        """Removes rows orphaned by postprocessing (cross-scanner dedup and
        root-cause grouping can collapse several streamed findings into one
        — see _resync_postprocessed_findings) — everything for this scan_id
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
        "verified": f.verified,
        "not_tested": f.not_tested,
        "raw": f.raw,
        "triage_status": f.triage_status.value,
        "excluded_path": f.excluded_path,
        "confidence": f.confidence,
        "original_severity": f.original_severity.value if f.original_severity else None,
        "epss_score": f.epss_score,
        "in_kev": f.in_kev,
        "dependency_scope": f.dependency_scope.value if f.dependency_scope else None,
        "corroborated_by": [t.value for t in f.corroborated_by],
        "occurrence_count": f.occurrence_count,
        "additional_locations": [loc.model_dump(mode="json") for loc in f.additional_locations],
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

    _resync_postprocessed_findings(rest, scan_id, user_id, scan.findings)

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

    _carry_forward_open_fix_prs(rest, user_id, scan.id, scan.findings)
    _push_to_defectdojo_best_effort(settings, durable_target, scan.id, scan.findings)
    _run_triage_best_effort(rest, settings, user_id, scan.findings, scan.id)


def _resync_postprocessed_findings(rest: _SyncRest, scan_id: UUID, user_id: str, findings: list[Finding]) -> None:
    """`on_findings` streams each stage's *raw* findings to Supabase as they
    complete, for a live-updating dashboard — but scanner-core's
    postprocess_findings() (fixture-path exclusion, cross-scanner dedup,
    root-cause grouping, EPSS/KEV, dependency scope) only runs once, on the
    complete set, right before run_pipeline() returns. Without this step the
    stored rows would keep the pre-postprocessing data: wrong severities,
    none of the new accuracy fields, and — for findings that dedup/grouping
    merged away — rows for findings that no longer exist in the final
    result at all. Re-upsert the final list (updates every surviving row in
    place, same ids), then delete whatever's left over."""
    if findings:
        rest.upsert("findings", [_finding_row(f, user_id) for f in findings], on_conflict="id")
    rest.delete_ids_not_in("findings", str(scan_id), [str(f.id) for f in findings])


def _carry_forward_open_fix_prs(
    rest: _SyncRest, user_id: str, scan_id: UUID, findings: list[Finding]
) -> None:
    """Re-attach an existing Fix It pull request to a finding that a fresh
    scan has reported again.

    A Fix It PR is opened as a *draft* against a branch — until someone
    merges it, the vulnerable code is still on the default branch, so a
    rescan finding it again is correct and suppressing it would be a lie.
    What was wrong is that the new finding arrived with no memory of the
    open PR, so the same issue looked untouched and inviting a second,
    duplicate fix.

    Matching is (title, file_path), the same equivalence autofix.py uses to
    decide whether a patch cleared a finding.
    """
    if not findings:
        return
    try:
        previous = rest.get("findings", {"user_id": user_id, "autofix_status": "fixed"})
    except httpx.HTTPError as exc:
        logger.warning("scan_service: could not read prior fix PRs: %s", exc)
        return

    by_key = {
        (str(row.get("title")), row.get("file_path")): row
        for row in previous
        if row.get("autofix_pr_url") and str(row.get("scan_id")) != str(scan_id)
    }
    if not by_key:
        return

    for finding in findings:
        prior = by_key.get((finding.title, finding.location.file_path))
        if not prior:
            continue
        rest.patch(
            "findings",
            {"id": str(finding.id), "user_id": user_id},
            {
                "autofix_status": "fixed",
                "autofix_pr_url": prior["autofix_pr_url"],
                # Deliberately NOT re-stamping autofix_at: no new pull
                # request was opened, so this must not consume another
                # auto-fix credit on every rescan.
            },
        )


def _run_triage_best_effort(
    rest: _SyncRest, settings: Settings, user_id: str, findings: list[Finding], scan_id_for_triage: UUID | None = None
) -> None:
    """LLM triage (addendum §2) — runs on every tier now, and never allowed to
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
