"""Fix It orchestration: generate a patch, prove it works, then open a draft PR.

The routers in routers/autofix.py stay a thin HTTP layer over this module, so the
single-finding and whole-scan entry points cannot drift apart on safety checks.

The load-bearing guarantee here is that a pull request is only ever opened
against a patch the originating scanner has re-run and stopped reporting. Every
failure path lands the finding in a terminal state with an honest reason rather
than leaving it on a spinner.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from aevrin_scanner_core import (
    Finding,
    Location,
    OwaspMcpCategory,
    Severity,
    ToolName,
    is_autofix_eligible,
)
from aevrin_scanner_core.execution.runner import ToolExecutionError
from fastapi import HTTPException, status

from aevrin_api.config import Settings
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.integrations.github_app import (
    GithubAppClient,
    GithubAppError,
    GithubAppUnavailable,
    install_url,
    parse_github_repo,
)
from aevrin_api.schemas import AutofixResponse
from aevrin_api.services.patcher import (
    CloneError,
    PatchFailed,
    cleanup_clone,
    clone_repo,
    generate_patch,
    reverify_finding,
    write_patched_file,
)
from aevrin_api.services.quota import QuotaExceeded, check_and_increment_quota, would_exceed_quota

logger = logging.getLogger("aevrin.autofix.service")

_NOT_CONFIGURED = "Auto-fix isn't configured yet."


def finding_from_row(row: dict[str, object]) -> Finding:
    """Reverses scan_service.py's _finding_row: reconstructs the typed
    scanner-core Finding the autofix flow needs from the flat DB row the
    dashboard/CLI already read this finding as."""
    additional: list[dict[str, object]] = row.get("additional_locations") or []  # type: ignore[assignment]
    return Finding(
        id=row["id"],  # type: ignore[arg-type]
        scan_id=row["scan_id"],  # type: ignore[arg-type]
        tool=ToolName(row["tool"]),
        owasp_category=OwaspMcpCategory(row["owasp_category"]),
        severity=Severity(row["severity"]),
        title=str(row["title"]),
        description=str(row["description"]),
        location=Location(
            file_path=row.get("file_path"),  # type: ignore[arg-type]
            line_start=row.get("line_start"),  # type: ignore[arg-type]
            line_end=row.get("line_end"),  # type: ignore[arg-type]
            manifest_field=row.get("manifest_field"),  # type: ignore[arg-type]
            tool_name_in_manifest=row.get("tool_name_in_manifest"),  # type: ignore[arg-type]
        ),
        remediation=str(row["remediation"]),
        verified=row.get("verified"),  # type: ignore[arg-type]
        not_tested=bool(row.get("not_tested")),
        excluded_path=bool(row.get("excluded_path")),
        additional_locations=[Location(**loc) for loc in additional],  # type: ignore[arg-type]
    )


async def mark_stage(db: SupabaseRest, finding_id: UUID, stage: str) -> None:
    """Record which step of the fix is running, for the progress dialog.

    Best-effort on purpose: this is presentation state, and failing a fix
    because a progress update didn't land would be backwards.
    """
    try:
        await db.update("findings", {"id": str(finding_id)}, {"autofix_stage": stage})
    except Exception:  # never let a progress write break a fix
        logger.debug("autofix: could not record stage %s for %s", stage, finding_id, exc_info=True)


async def mark_autofix(
    db: SupabaseRest,
    finding_id: UUID,
    status_value: str,
    *,
    pr_url: str | None = None,
    reason: str | None = None,
) -> None:
    patch: dict[str, Any] = {
        "autofix_status": status_value,
        "autofix_pr_url": pr_url,
        "autofix_failure_reason": reason,
        # Every status this sets is terminal or idle, so no step is running.
        "autofix_stage": None,
    }
    # Stamped only on success, and only in Postgres; this is what makes the
    # auto_fix usage counter recoverable when Redis can't be reached. A PR
    # that exists must always be countable.
    if status_value == "fixed":
        patch["autofix_at"] = datetime.now(UTC).isoformat()
    await db.update("findings", {"id": str(finding_id)}, patch)


def _unreachable(exc: GithubAppError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not reach GitHub: {exc}")


async def _resolve_repo(
    row: dict[str, Any], db: SupabaseRest, settings: Settings
) -> tuple[str, str, GithubAppClient]:
    """The repository this finding belongs to, plus a usable App client.

    Everything raised here is repository-wide rather than finding-specific, so a
    bulk run should stop instead of marking one finding failed.
    """
    scan_rows = await db.select("scans", {"id": str(row["scan_id"])})
    if not scan_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The scan this finding belongs to no longer exists.",
        )
    repo = parse_github_repo(str(scan_rows[0]["target"]))
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Fix It only supports GitHub repository scans.",
        )
    if not settings.github_app_slug:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NOT_CONFIGURED)
    try:
        client = GithubAppClient(settings)
    except GithubAppUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NOT_CONFIGURED
        ) from None
    return (*repo, client)


async def _read_target_file(
    client: GithubAppClient, owner: str, name: str, file_path: str, installation_id: int
) -> tuple[str, str, str]:
    """Returns (token, file_content, file_sha) for the default branch."""
    try:
        token = (await client.create_installation_token(installation_id)).token
        file_result = await client.get_file(owner, name, file_path, token)
    except GithubAppError as exc:
        raise _unreachable(exc) from exc
    if file_result is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not read this finding's file from the repository's default branch.",
        )
    content, sha = file_result
    return token, content, sha


async def _verify_in_clone(
    settings: Settings,
    finding: Finding,
    file_content: str,
    patched: str,
    clone_url: str,
    token: str,
) -> tuple[str, bool, str | None]:
    """Applies the drafted patch to a throwaway clone and re-runs the scanner.

    Returns (patched_source, cleared, failure). One retry is allowed, fed the
    scanner's own complaint. `failure` being set means we could not establish
    whether the fix holds, which is treated exactly like a failed fix: no PR.
    """
    # Guaranteed non-None by is_autofix_eligible, which every caller runs
    # first; asserted rather than assumed so a future caller that skips
    # that check fails here instead of deep inside the patch writer.
    assert finding.location.file_path is not None
    file_path = finding.location.file_path
    cleared = False
    failure: str | None = None
    repo_dir = None
    try:
        repo_dir = clone_repo(clone_url, token=token)
        write_patched_file(repo_dir, file_path, patched)
        cleared = reverify_finding(finding, repo_dir)
        if not cleared:
            try:
                patched = await generate_patch(
                    settings,
                    finding,
                    file_content,
                    retry_feedback=f"{finding.tool.value} still reported this finding after the first patch.",
                )
            except PatchFailed:
                # The first patch stands as the best attempt; it just didn't
                # clear, which the caller's `not cleared` branch reports.
                logger.info("autofix: retry could not be drafted for %s", finding.id, exc_info=True)
            else:
                write_patched_file(repo_dir, file_path, patched)
                cleared = reverify_finding(finding, repo_dir)
    except CloneError as exc:
        failure = f"Could not clone the repository to verify the fix: {exc}"
    except ToolExecutionError as exc:
        # Fail closed: a scanner that couldn't run is not evidence the finding
        # is gone, and this flow's whole promise is that a PR is only ever
        # opened against a re-verified fix.
        logger.warning("autofix: re-verification could not run for %s", finding.id, exc_info=True)
        failure = f"Could not re-run {finding.tool.value} to verify the fix, so no pull request was opened ({exc})."
    except OSError as exc:
        logger.warning("autofix: filesystem error verifying %s", finding.id, exc_info=True)
        failure = f"Could not write the patched file while verifying the fix: {exc}"
    finally:
        if repo_dir:
            cleanup_clone(repo_dir)

    return patched, cleared, failure


async def _open_fix_pr(
    client: GithubAppClient,
    owner: str,
    name: str,
    token: str,
    finding: Finding,
    finding_id: UUID,
    patched: str,
    file_sha: str,
) -> str:
    # Same guarantee as _verify_in_clone: is_autofix_eligible has already
    # rejected any finding without a file location before we get here.
    assert finding.location.file_path is not None
    base_branch, base_sha = await client.get_default_branch_head_sha(owner, name, token)
    fix_branch = f"aevrin-fix-{str(finding_id)[:8]}"
    await client.create_branch(owner, name, token, fix_branch, base_sha)
    await client.commit_file(
        owner,
        name,
        token,
        path=finding.location.file_path,
        content=patched,
        message=f"Fix: {finding.title}",
        branch=fix_branch,
        sha=file_sha,
    )
    body = (
        f"Automatically generated by [Aevrin](https://mcp.aevrin.net)'s Fix It to resolve a finding from a security scan.\n\n"
        f"**Finding:** {finding.title}\n"
        f"**OWASP MCP category:** {finding.owasp_category.value}\n"
        f"**Severity:** {finding.severity.value}\n"
        f"**File:** {finding.location.file_path}\n\n"
        f"{finding.description}\n\n"
        f"This patch was re-verified against the original scanner (`{finding.tool.value}`) before this PR was opened, "
        f"it no longer reports this finding. This is a draft PR; review it like any other change before merging."
    )
    return await client.open_draft_pr(
        owner, name, token, title=f"Fix: {finding.title}", body=body, head=fix_branch, base=base_branch
    )


async def run_fix_for_row(
    row: dict[str, Any],
    user: AuthenticatedUser,
    db: SupabaseRest,
    settings: Settings,
) -> AutofixResponse:
    """The fix pipeline for one finding, shared by the single-finding endpoint
    and the whole-scan one.

    Raises HTTPException only for conditions that apply to the whole repository
    (not a GitHub repo scan, App not installed, GitHub unreachable); per-finding
    failures come back as a `failed` response so a bulk run can carry on.
    """
    finding_id = UUID(str(row["id"]))
    finding = finding_from_row(row)
    owner, name, client = await _resolve_repo(row, db, settings)

    await mark_stage(db, finding_id, "authorizing")
    try:
        installation_id = await client.get_repo_installation_id(owner, name)
    except GithubAppError as exc:
        raise _unreachable(exc) from exc
    if installation_id is None:
        return AutofixResponse(status="needs_github_connection", install_url=install_url(settings, user.id))

    assert finding.location.file_path is not None  # enforced by is_autofix_eligible
    token, file_content, file_sha = await _read_target_file(
        client, owner, name, finding.location.file_path, installation_id
    )

    await mark_autofix(db, finding_id, "in_progress")
    await mark_stage(db, finding_id, "analysing")

    await mark_stage(db, finding_id, "generating")
    try:
        patched = await generate_patch(settings, finding, file_content)
    except PatchFailed as exc:
        # The reason comes from the failure itself rather than being guessed
        # here, so what the user reads matches what actually happened.
        return await _fail(db, finding_id, str(exc))

    await mark_stage(db, finding_id, "verifying")
    patched, cleared, failure = await _verify_in_clone(
        settings, finding, file_content, patched, f"https://github.com/{owner}/{name}.git", token
    )

    if failure:
        return await _fail(db, finding_id, failure)
    if not cleared:
        # A patch *was* drafted; it just didn't hold up. Saying it "couldn't be
        # generated" described the wrong step and sent people looking in the
        # wrong place.
        return await _fail(
            db,
            finding_id,
            f"A fix was drafted, but {finding.tool.value} still reported this finding afterwards, "
            "so no pull request was opened. It needs a manual fix.",
        )

    await mark_stage(db, finding_id, "opening_pr")
    try:
        pr_url = await _open_fix_pr(
            client, owner, name, token, finding, finding_id, patched, file_sha
        )
    except GithubAppError as exc:
        return await _fail(db, finding_id, f"Fix generated and verified, but opening the pull request failed: {exc}")

    await mark_autofix(db, finding_id, "fixed", pr_url=pr_url)
    try:
        await check_and_increment_quota(settings, db, user.id, "auto_fix")
    except QuotaExceeded:
        # The PR is real and already open, nothing to roll back. This only
        # happens under concurrent Fix It calls landing right at the limit.
        pass
    return AutofixResponse(status="fixed", pr_url=pr_url)


async def _fail(db: SupabaseRest, finding_id: UUID, reason: str) -> AutofixResponse:
    await mark_autofix(db, finding_id, "failed", reason=reason)
    return AutofixResponse(status="failed", failure_reason=reason)


def eligible_candidates(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Splits findings into what Fix It can attempt and how many it cannot.

    Highest severity first, so a quota ceiling hit part-way through spends the
    remaining allowance on what matters most.
    """
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    candidates = []
    skipped = 0
    for row in rows:
        already_settled = row.get("autofix_status") == "fixed" or row.get("triage_status") != "open"
        if already_settled or not is_autofix_eligible(finding_from_row(row))[0]:
            skipped += 1
        else:
            candidates.append(row)
    candidates.sort(key=lambda r: order.get(str(r.get("severity")), 9))
    return candidates, skipped


async def run_bulk_fix(
    candidates: list[dict[str, Any]],
    user: AuthenticatedUser,
    db: SupabaseRest,
    settings: Settings,
) -> None:
    """Sequential on purpose: each fix clones a repo and runs a scanner, and
    running several of those at once on one API container is how you turn a
    fix run into an outage for everyone else."""
    scan_id = str(candidates[0]["scan_id"]) if candidates else None

    for row in candidates:
        finding_id = UUID(str(row["id"]))

        # Checked between findings, so a cancel never interrupts a fix that is
        # already generating, cloning, or opening a pull request.
        if scan_id:
            current = await db.select("scans", {"id": scan_id}, columns="autofix_cancel_requested_at", limit=1)
            if current and current[0].get("autofix_cancel_requested_at"):
                logger.info("bulk fix: cancelled before finding %s", finding_id)
                await mark_autofix(db, finding_id, "none")
                continue

        if await would_exceed_quota(settings, db, user.id, "auto_fix"):
            await mark_autofix(
                db,
                finding_id,
                "failed",
                reason="Stopped at your monthly auto-fix limit. Buy +10 more from billing, or wait for the reset.",
            )
            continue
        try:
            await run_fix_for_row(row, user, db, settings)
        except HTTPException as exc:
            await mark_autofix(db, finding_id, "failed", reason=str(exc.detail))
        except Exception:
            logger.exception("bulk fix: unexpected failure on finding %s", finding_id)
            await mark_autofix(
                db, finding_id, "failed", reason="An unexpected error stopped this fix. Try it on its own."
            )
