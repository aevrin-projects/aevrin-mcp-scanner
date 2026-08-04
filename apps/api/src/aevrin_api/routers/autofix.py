"""Fix It — auto-fix pull requests (V5 prompt §7/§8).

Two genuinely separate GitHub concerns meet here: the App-based
install/callback flow that grants real repo access ("Connect GitHub for
Auto-Fix"), and the fix orchestration itself (generate -> re-verify -> open
draft PR), gated by the auto_fix quota bucket. CLI parity for the second
half lives in packages/cli's `aevrin fix` command, which calls the same
POST /findings/{id}/fix endpoint below.
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from aevrin_scanner_core import (
    Finding,
    Location,
    OwaspMcpCategory,
    Severity,
    ToolName,
    is_autofix_eligible,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from ..autofix import (
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
from ..schemas import AutofixResponse, GithubInstallUrlResponse, GithubStatusResponse
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
) -> RedirectResponse:
    """GitHub redirects the person's browser here after they approve (or
    cancel) installing the App — not an authenticated API call, so identity
    comes entirely from `state` (see sign_install_state)."""
    settings_url = f"{settings.web_origin}/dashboard/settings"
    if not installation_id or not state:
        return RedirectResponse(f"{settings_url}?github=cancelled")
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
    await db.update(
        "findings",
        {"id": str(finding_id)},
        {"autofix_status": status_value, "autofix_pr_url": pr_url, "autofix_failure_reason": reason},
    )


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

    repo_dir = None
    try:
        repo_dir = clone_repo(f"https://github.com/{owner}/{name}")
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
    finally:
        if repo_dir:
            cleanup_clone(repo_dir)

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
