"""Fix It — auto-fix pull requests (V5 prompt §7/§8).

Two genuinely separate GitHub concerns meet here: the App-based
install/callback flow that grants real repo access ("Connect GitHub for
Auto-Fix"), and the fix orchestration itself (generate -> re-verify -> open
draft PR), gated by the auto_fix quota bucket. CLI parity for the second
half lives in packages/cli's `aevrin fix` command, which calls the same
POST /findings/{id}/fix endpoint below.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from aevrin_scanner_core import (
    Finding,
    Location,
    OwaspMcpCategory,
    Severity,
    ToolName,
    is_autofix_eligible,
)
from aevrin_scanner_core.runner import ToolExecutionError
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from ..autofix import (
    CloneError,
    cleanup_clone,
    clone_repo,
    generate_patch,
    reverify_finding,
    write_patched_file,
)
from ..config import Settings, get_settings
from ..db import SupabaseRest
from ..deps import get_current_user, get_db, get_user_from_jwt_or_api_key
from ..github_app import (
    GithubAppClient,
    GithubAppError,
    GithubAppUnavailable,
    parse_github_repo,
    sign_install_state,
    verify_install_state,
)
from ..quota import (
    QuotaExceeded,
    check_and_increment_quota,
    effective_tier,
    get_or_create_account,
    would_exceed_quota,
)
from ..schemas import (
    AutofixResponse,
    BulkFixResponse,
    GithubInstallUrlResponse,
    GithubRepoOut,
    GithubReposResponse,
    GithubStatusResponse,
)
from ..security import AuthenticatedUser

router = APIRouter(tags=["autofix"])
logger = logging.getLogger("aevrin.autofix.router")


def finding_from_row(row: dict[str, object]) -> Finding:
    """Reverses scan_service.py's _finding_row — reconstructs the typed
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


@router.get("/github/status", response_model=GithubStatusResponse)
async def github_status(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
) -> GithubStatusResponse:
    rows = await db.select("github_installations", {"user_id": user.id}, order="created_at.desc", limit=1)
    if not rows:
        return GithubStatusResponse(connected=False)
    return GithubStatusResponse(connected=True, account_login=rows[0]["account_login"])


def _install_url(settings: Settings, user_id: str) -> str:
    state = sign_install_state(settings, user_id)
    return f"https://github.com/apps/{settings.github_app_slug}/installations/new?state={state}"


@router.get("/github/repos", response_model=GithubReposResponse)
async def github_repos(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    labels: Annotated[bool, Query()] = True,
) -> GithubReposResponse:
    """Repositories this person's installation can reach, for the scan
    picker and for deciding where Fix It can actually work.

    Scoped to the installation, so it reflects exactly what they granted at
    install time — a few hand-picked repos or all of them — rather than
    every repo their GitHub account can see.
    """
    rows = await db.select("github_installations", {"user_id": user.id}, order="created_at.desc", limit=1)
    if not rows:
        return GithubReposResponse(connected=False, repos=[])

    try:
        client = GithubAppClient(settings)
    except GithubAppUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GitHub integration isn't configured yet."
        ) from None

    try:
        token = (await client.create_installation_token(int(rows[0]["installation_id"]))).token
        repos = await client.list_installation_repos(token)
    except GithubAppError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not reach GitHub: {exc}") from exc

    out = [
        GithubRepoOut(
            full_name=str(repo.get("full_name", "")),
            html_url=str(repo.get("html_url", "")),
            private=bool(repo.get("private")),
            default_branch=str(repo.get("default_branch") or "main"),
            pushed_at=repo.get("pushed_at"),
            looks_like_mcp=None,
        )
        for repo in repos
    ]

    # MCP detection is a label, never a gate — see looks_like_mcp_repo.
    #
    # It costs up to six GitHub calls per repository, and running that
    # sequentially over 30 repos made this endpoint take tens of seconds.
    # This route is also what the finding page consults to decide whether
    # Fix It can run, so a slow answer here showed up as a Fix It button
    # greyed out on a paid, connected account — a label nobody asked for
    # blocking the feature people pay for.
    #
    # Now: bounded concurrency, a hard overall time budget, and unlabelled
    # (None) results if the budget runs out. Never fails the request.
    if labels:
        semaphore = asyncio.Semaphore(6)

        async def label(index: int, repo: dict[str, Any]) -> None:
            owner_login = str(repo.get("owner", {}).get("login", ""))
            name = str(repo.get("name", ""))
            if not owner_login or not name:
                return
            async with semaphore:
                out[index].looks_like_mcp = await client.looks_like_mcp_repo(owner_login, name, token)

        try:
            await asyncio.wait_for(
                asyncio.gather(*(label(i, r) for i, r in enumerate(repos[:30])), return_exceptions=True),
                timeout=8.0,
            )
        except TimeoutError:
            logger.info("github repos: MCP labelling exceeded its budget, returning unlabelled")

    return GithubReposResponse(connected=True, account_login=rows[0]["account_login"], repos=out)


@router.get("/github/install-url", response_model=GithubInstallUrlResponse)
async def github_install_url(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GithubInstallUrlResponse:
    if not settings.github_app_slug:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auto-fix isn't configured yet.")
    return GithubInstallUrlResponse(url=_install_url(settings, user.id))


@router.get("/github/callback")
async def github_callback(
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    installation_id: Annotated[int | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    code: Annotated[str | None, Query()] = None,
    setup_action: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """GitHub redirects the person's browser here after they approve (or
    cancel) installing the App — not an authenticated API call, so identity
    comes entirely from `state` (see sign_install_state).

    GitHub sends four materially different shapes here and this used to
    collapse three of them into a single misleading "cancelled":

      installation_id + state   a normal install started from our link
      installation_id, no state installed from GitHub's own App page, so
                                there is no signed state to attribute it to
      code, no installation_id  the App was *authorized* but not installed
      setup_action=request      an org owner still has to approve it

    Someone who genuinely granted access and then saw "cancelled" has no way
    to tell what went wrong, which is exactly the reported symptom: approve,
    land back, nothing updated, no explanation.
    """
    settings_url = f"{settings.web_origin}/settings/billing"

    if setup_action == "request":
        return RedirectResponse(f"{settings_url}?github=approval_pending")

    if not installation_id:
        # Authorized but nothing installed — the App grants repo access via
        # an *installation*, and user authorization alone doesn't create one.
        reason = "authorized_not_installed" if code else "cancelled"
        return RedirectResponse(f"{settings_url}?github={reason}")

    if not state:
        # No signed state, which happens in two very different situations.
        #
        # With "Redirect on update" enabled on the App, an *existing* install
        # comes back here every time someone changes which repositories are
        # granted — and that redirect carries no state, because it didn't
        # start from our signed link. If we already store this installation,
        # the binding is established and this is simply an update; telling a
        # connected user to reconnect would be both wrong and alarming.
        known = await db.select("github_installations", {"installation_id": str(installation_id)}, limit=1)
        if known:
            return RedirectResponse(f"{settings_url}?github=updated")

        # Otherwise it's a first-time install started from GitHub's own App
        # page. Deliberately not auto-claimed for whoever is signed in in
        # this browser: that would let anyone reaching this URL bind someone
        # else's organization installation to their own account.
        logger.info("github callback: installation %s arrived without signed state", installation_id)
        return RedirectResponse(f"{settings_url}?github=needs_relink")

    user_id = verify_install_state(settings, state)
    if not user_id:
        return RedirectResponse(f"{settings_url}?github=invalid_state")
    try:
        client = GithubAppClient(settings)
        installation = await client.get_installation(installation_id)
    except (GithubAppUnavailable, GithubAppError):
        logger.warning("github callback: could not resolve installation %s", installation_id, exc_info=True)
        return RedirectResponse(f"{settings_url}?github=error")
    account = installation.get("account", {})
    await db.insert(
        "github_installations",
        {
            "user_id": user_id,
            "installation_id": installation_id,
            "account_login": account.get("login", "unknown"),
            "account_type": account.get("type", "User"),
        },
        upsert_on="installation_id",
    )
    return RedirectResponse(f"{settings_url}?github=connected")


async def _mark_autofix(db: SupabaseRest, finding_id: UUID, status_value: str, *, pr_url: str | None = None, reason: str | None = None) -> None:
    patch: dict[str, Any] = {
        "autofix_status": status_value,
        "autofix_pr_url": pr_url,
        "autofix_failure_reason": reason,
    }
    # Stamped only on success, and only in Postgres — this is what makes the
    # auto_fix usage counter recoverable when Redis can't be reached. A PR
    # that exists must always be countable.
    if status_value == "fixed":
        patch["autofix_at"] = datetime.now(UTC).isoformat()
    await db.update("findings", {"id": str(finding_id)}, patch)


@router.post("/findings/{finding_id}/fix", response_model=AutofixResponse)
async def fix_finding(
    finding_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_user_from_jwt_or_api_key)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AutofixResponse:
    account = await get_or_create_account(db, user.id)
    if effective_tier(account) not in ("pro", "team"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Fix It is available on Pro and Team plans.")

    rows = await db.select("findings", {"id": str(finding_id), "user_id": user.id})
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    row = rows[0]
    if row.get("autofix_status") == "fixed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This finding already has an open fix PR.")

    finding = finding_from_row(row)
    fixable, reason = is_autofix_eligible(finding)
    if not fixable:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=reason)

    exceeded = await would_exceed_quota(settings, db, user.id, "auto_fix")
    if exceeded:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Monthly auto-fix limit reached ({exceeded.limit}/month). "
                f"Buy +10 more from account settings, or it resets {exceeded.resets_at.date().isoformat()}."
            ),
        )

    return await _run_fix_for_row(row, user, db, settings)


async def _run_fix_for_row(
    row: dict[str, Any],
    user: AuthenticatedUser,
    db: SupabaseRest,
    settings: Settings,
) -> AutofixResponse:
    """The actual fix pipeline for one finding, shared by the single-finding
    endpoint and the whole-scan one so their safety checks cannot drift.

    Raises HTTPException only for conditions that apply to the whole
    repository (not a GitHub repo scan, App not installed, GitHub
    unreachable); per-finding failures come back as a `failed` response so a
    bulk run can carry on with the rest.
    """
    finding_id = UUID(str(row["id"]))
    finding = finding_from_row(row)

    scan_rows = await db.select("scans", {"id": str(row["scan_id"])})
    if not scan_rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="The scan this finding belongs to no longer exists.")
    repo = parse_github_repo(str(scan_rows[0]["target"]))
    if repo is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Fix It only supports GitHub repository scans.")
    owner, name = repo

    if not settings.github_app_slug:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auto-fix isn't configured yet.")
    try:
        client = GithubAppClient(settings)
    except GithubAppUnavailable:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auto-fix isn't configured yet.") from None

    try:
        installation_id = await client.get_repo_installation_id(owner, name)
    except GithubAppError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not reach GitHub: {exc}") from exc
    if installation_id is None:
        return AutofixResponse(status="needs_github_connection", install_url=_install_url(settings, user.id))

    try:
        token_obj = await client.create_installation_token(installation_id)
        token = token_obj.token
        assert finding.location.file_path is not None  # enforced by is_autofix_eligible above
        file_result = await client.get_file(owner, name, finding.location.file_path, token)
    except GithubAppError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not reach GitHub: {exc}") from exc
    if file_result is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Could not read this finding's file from the repository's default branch.")
    file_content, file_sha = file_result

    await _mark_autofix(db, finding_id, "in_progress")

    patched = await generate_patch(settings, finding, file_content)
    if patched is None:
        await _mark_autofix(db, finding_id, "failed", reason="Could not generate a fix — the model is unavailable or the file is too large.")
        return AutofixResponse(status="failed", failure_reason="Could not generate a fix for this finding.")

    # Everything below runs against a throwaway clone. Any failure in here
    # used to escape as an unhandled 500 *after* the finding was already
    # marked in_progress at line above — leaving it stuck on a spinner
    # forever with no reason recorded. Every failure path now lands the
    # finding in a terminal "failed" state with an honest reason.
    cleared = False
    failure: str | None = None
    repo_dir = None
    try:
        repo_dir = clone_repo(f"https://github.com/{owner}/{name}.git", token=token)
        write_patched_file(repo_dir, finding.location.file_path, patched)
        cleared = reverify_finding(finding, repo_dir)
        if not cleared:
            retry_patched = await generate_patch(
                settings, finding, file_content, retry_feedback=f"{finding.tool.value} still reported this finding after the first patch."
            )
            if retry_patched is not None:
                patched = retry_patched
                write_patched_file(repo_dir, finding.location.file_path, patched)
                cleared = reverify_finding(finding, repo_dir)
    except CloneError as exc:
        failure = f"Could not clone the repository to verify the fix: {exc}"
    except ToolExecutionError as exc:
        # Fail closed: a scanner that couldn't run is not evidence the
        # finding is gone, and this flow's whole promise is that a PR is
        # only ever opened against a re-verified fix.
        logger.warning("autofix: re-verification could not run for finding %s", finding_id, exc_info=True)
        failure = f"Could not re-run {finding.tool.value} to verify the fix, so no pull request was opened ({exc})."
    except OSError as exc:
        logger.warning("autofix: filesystem error verifying finding %s", finding_id, exc_info=True)
        failure = f"Could not write the patched file while verifying the fix: {exc}"
    finally:
        if repo_dir:
            cleanup_clone(repo_dir)

    if failure:
        await _mark_autofix(db, finding_id, "failed", reason=failure)
        return AutofixResponse(status="failed", failure_reason=failure)

    if not cleared:
        reason = "An automatic fix couldn't be generated for this finding — it may need manual review."
        await _mark_autofix(db, finding_id, "failed", reason=reason)
        return AutofixResponse(status="failed", failure_reason=reason)

    try:
        base_branch, base_sha = await client.get_default_branch_head_sha(owner, name, token)
        fix_branch = f"aevrin-fix-{str(finding_id)[:8]}"
        await client.create_branch(owner, name, token, fix_branch, base_sha)
        await client.commit_file(
            owner, name, token,
            path=finding.location.file_path,
            content=patched,
            message=f"Fix: {finding.title}",
            branch=fix_branch,
            sha=file_sha,
        )
        pr_body = (
            f"Automatically generated by [Aevrin](https://mcp.aevrin.net)'s Fix It to resolve a finding from a security scan.\n\n"
            f"**Finding:** {finding.title}\n"
            f"**OWASP MCP category:** {finding.owasp_category.value}\n"
            f"**Severity:** {finding.severity.value}\n"
            f"**File:** {finding.location.file_path}\n\n"
            f"{finding.description}\n\n"
            f"This patch was re-verified against the original scanner (`{finding.tool.value}`) before this PR was opened — "
            f"it no longer reports this finding. This is a draft PR; review it like any other change before merging."
        )
        pr_url = await client.open_draft_pr(
            owner, name, token, title=f"Fix: {finding.title}", body=pr_body, head=fix_branch, base=base_branch
        )
    except GithubAppError as exc:
        reason = f"Fix generated and verified, but opening the pull request failed: {exc}"
        await _mark_autofix(db, finding_id, "failed", reason=reason)
        return AutofixResponse(status="failed", failure_reason=reason)

    await _mark_autofix(db, finding_id, "fixed", pr_url=pr_url)
    try:
        await check_and_increment_quota(settings, db, user.id, "auto_fix")
    except QuotaExceeded:
        # The PR is real and already open — nothing to roll back. This only
        # happens under concurrent Fix It calls landing right at the limit.
        pass
    return AutofixResponse(status="fixed", pr_url=pr_url)


@router.post("/scans/{scan_id}/fix/cancel")
async def cancel_scan_fix(
    scan_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_user_from_jwt_or_api_key)],
    db: Annotated[SupabaseRest, Depends(get_db)],
) -> dict[str, Any]:
    """Stop a whole-scan Fix It run.

    Cancellation is checked *between* findings, never mid-fix. Aborting a fix
    already in flight would risk a half-applied patch or an orphaned branch on
    someone's repository, which is worse than waiting a few seconds for the
    current one to finish. Anything still queued is returned to its untouched
    state so those rows stop showing a spinner.
    """
    rows = await db.select("scans", {"id": str(scan_id), "user_id": user.id}, limit=1)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")

    await db.update(
        "scans", {"id": str(scan_id), "user_id": user.id},
        {"autofix_cancel_requested_at": datetime.now(UTC).isoformat()},
    )

    queued = await db.select(
        "findings", {"scan_id": str(scan_id), "user_id": user.id, "autofix_status": "queued"}, columns="id"
    )
    for row in queued:
        await _mark_autofix(db, UUID(str(row["id"])), "none")

    return {"cancelled": True, "released": len(queued)}


@router.post("/scans/{scan_id}/fix", response_model=BulkFixResponse)
async def fix_scan(
    scan_id: UUID,
    background_tasks: BackgroundTasks,
    user: Annotated[AuthenticatedUser, Depends(get_user_from_jwt_or_api_key)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BulkFixResponse:
    """Fix every eligible open finding in one scan, in one action.

    Runs the same per-finding pipeline (generate -> apply to a throwaway
    clone -> re-run the originating scanner -> only then open a draft PR),
    so nothing here weakens the guarantee that a PR is never opened against
    an unverified fix. One PR per finding rather than one combined branch:
    each is independently reviewable and independently revertable, and a
    single bad patch can't hold up the rest.

    Findings that aren't auto-fixable (a dependency CVE, a finding with no
    file path, an already-fixed one) are counted as skipped rather than
    failed — they were never candidates, and reporting them as failures
    would make a healthy run look broken.
    """
    account = await get_or_create_account(db, user.id)
    if effective_tier(account) not in ("pro", "team"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Fix It is available on Pro and Team plans.")

    scan_rows = await db.select("scans", {"id": str(scan_id), "user_id": user.id})
    if not scan_rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")

    rows = await db.select("findings", {"scan_id": str(scan_id), "user_id": user.id})
    candidates: list[dict[str, Any]] = []
    skipped = 0
    for row in rows:
        if row.get("autofix_status") == "fixed" or row.get("triage_status") != "open":
            skipped += 1
            continue
        fixable, _reason = is_autofix_eligible(finding_from_row(row))
        if not fixable:
            skipped += 1
            continue
        candidates.append(row)

    if not candidates:
        return BulkFixResponse(
            attempted=0, fixed=0, failed=0, skipped=skipped, pr_urls=[],
            message="No findings in this scan can be fixed automatically. Dependency CVEs and findings without a file location need a manual change.",
        )

    # Highest severity first, so a quota ceiling hit part-way through spends
    # the remaining allowance on what matters most.
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    candidates.sort(key=lambda r: order.get(str(r.get("severity")), 9))

    # Mark every candidate queued up front, then run them in the background.
    #
    # A single fix takes tens of seconds (a model call, a clone, a scanner
    # re-run, then GitHub), so a scan with several findings held the request
    # open for minutes with nothing to show for it. The client polls the
    # findings it already renders and watches autofix_status move
    # queued -> in_progress -> fixed/failed per finding, which is real
    # progress rather than a spinner.
    # A cancel from a previous run must not immediately stop this one.
    await db.update("scans", {"id": str(scan_id), "user_id": user.id}, {"autofix_cancel_requested_at": None})

    for row in candidates:
        await _mark_autofix(db, UUID(str(row["id"])), "queued")

    background_tasks.add_task(_run_bulk_fix, candidates, user, db, settings)

    return BulkFixResponse(
        attempted=len(candidates), fixed=0, failed=0, skipped=skipped, pr_urls=[],
        message=(
            f"Fixing {len(candidates)} finding{'s' if len(candidates) != 1 else ''} in the background"
            + (f"; {skipped} can't be fixed automatically" if skipped else "")
            + ". Progress appears on each finding below."
        ),
    )


async def _run_bulk_fix(
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

        # Checked between findings, so a cancel never interrupts a fix that
        # is already generating, cloning, or opening a pull request.
        if scan_id:
            current = await db.select("scans", {"id": scan_id}, columns="autofix_cancel_requested_at", limit=1)
            if current and current[0].get("autofix_cancel_requested_at"):
                logger.info("bulk fix: cancelled before finding %s", finding_id)
                await _mark_autofix(db, finding_id, "none")
                continue

        if await would_exceed_quota(settings, db, user.id, "auto_fix"):
            await _mark_autofix(
                db, finding_id, "failed",
                reason="Stopped at your monthly auto-fix limit. Buy +10 more from billing, or wait for the reset.",
            )
            continue
        try:
            await _run_fix_for_row(row, user, db, settings)
        except HTTPException as exc:
            await _mark_autofix(db, finding_id, "failed", reason=str(exc.detail))
        except Exception:
            logger.exception("bulk fix: unexpected failure on finding %s", finding_id)
            await _mark_autofix(
                db, finding_id, "failed", reason="An unexpected error stopped this fix. Try it on its own."
            )
