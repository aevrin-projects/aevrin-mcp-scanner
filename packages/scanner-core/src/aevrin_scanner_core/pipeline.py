"""The one pipeline both apps/api and packages/cli run — this is what keeps
findings from drifting into different vocabularies between the website, the
CLI, and the hook. Callers supply an `on_stage` callback for side effects
(DB writes for the web polling UI, terminal printing for the CLI) and get
back a fully-populated Scan.

GitHub-repo targets get the full tool set. Live-server and pasted-config
targets only get manifest-level checks (mcp-shield/mcp-scan/manifest rules)
per Section 6 — cloning/static-analysis/secrets/dependency stages are marked
SKIPPED, not silently absent.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from .adapters import (
    BanditAdapter,
    GitleaksAdapter,
    McpContextProtectorAdapter,
    McpScanAdapter,
    McpShieldAdapter,
    OsvScannerAdapter,
    ScorecardAdapter,
    SemgrepAdapter,
    TrivyAdapter,
    TruffleHogAdapter,
)
from .adapters.mcp_shield import build_mcp_config
from .manifest_rules import (
    TransportInfo,
    check_audit_logging_presence,
    check_weak_auth,
)
from .models import Finding, Scan, ScanStage, ScanStatus, StageName, StageStatus, TargetType
from .not_tested import not_tested_placeholder
from .rug_pull import PinnedSignature, diff_signatures, hash_signature
from .runner import ToolExecutionError
from .scoring import compute_score

OnStage = Callable[[ScanStage], None]
OnFindings = Callable[[list[Finding]], None]


@dataclass
class PipelineConfig:
    github_token: str | None = None
    clone_depth: int = 50
    # {server_name: signature_hash} from the last scan of this exact target —
    # empty on first scan, populated by the caller from persisted state.
    previous_signatures: dict[str, str] = field(default_factory=dict)
    # (server_name, signature_hash) pairs computed this run — caller persists
    # these after the pipeline returns so the *next* scan can diff against them.
    computed_signatures: list[tuple[str, str]] = field(default_factory=list)


class PipelineError(Exception):
    pass


def _mark(stage: ScanStage, status: StageStatus, on_stage: OnStage, error: str | None = None) -> None:
    stage.status = status
    stage.error = error
    if status == StageStatus.RUNNING:
        stage.started_at = datetime.now(UTC)
    elif status in (StageStatus.DONE, StageStatus.FAILED, StageStatus.SKIPPED):
        stage.finished_at = datetime.now(UTC)
    on_stage(stage)


def _run_isolated(label: str, fn: Callable[[], list[Finding]]) -> tuple[list[Finding], str | None]:
    try:
        return fn(), None
    except ToolExecutionError as exc:
        return [], f"{label}: {exc}"
    except Exception as exc:  # noqa: BLE001 - a crashing adapter must never take down the scan
        return [], f"{label}: unexpected error: {exc}"


def run_pipeline(
    target_type: TargetType,
    target: str,
    config: PipelineConfig,
    on_stage: OnStage,
    on_findings: OnFindings,
    scan_id: UUID | None = None,
) -> Scan:
    scan_id = scan_id or uuid4()
    scan = Scan(id=scan_id, target_type=target_type, target=target, status=ScanStatus.RUNNING)
    scan.stages = [ScanStage(scan_id=scan_id, name=name) for name in StageName]
    stage_by_name = {s.name: s for s in scan.stages}
    errors: list[str] = []

    def emit(findings: list[Finding]) -> None:
        scan.findings.extend(findings)
        if findings:
            on_findings(findings)

    workdir = tempfile.mkdtemp(prefix="aevrin-scan-")
    try:
        repo_dir = None
        if target_type == TargetType.GITHUB_REPO:
            repo_dir = _run_clone_stage(target, workdir, config, stage_by_name[StageName.CLONING], on_stage, errors)
            _run_static_analysis_stage(scan_id, repo_dir, stage_by_name[StageName.STATIC_ANALYSIS], on_stage, emit, errors)
            _run_secrets_stage(scan_id, repo_dir, stage_by_name[StageName.SECRETS], on_stage, emit, errors)
            _run_dependencies_stage(
                scan_id, repo_dir, target, config, stage_by_name[StageName.DEPENDENCIES], on_stage, emit, errors
            )
        elif target_type == TargetType.LOCAL_PATH:
            # CLI scanning the user's own machine — nothing to clone, the
            # target IS the directory to scan. Not a git URL, so Scorecard
            # (github-repo-only) is skipped inside _run_dependencies_stage.
            repo_dir = target
            _mark(stage_by_name[StageName.CLONING], StageStatus.SKIPPED, on_stage)
            _run_static_analysis_stage(scan_id, repo_dir, stage_by_name[StageName.STATIC_ANALYSIS], on_stage, emit, errors)
            _run_secrets_stage(scan_id, repo_dir, stage_by_name[StageName.SECRETS], on_stage, emit, errors)
            _run_dependencies_stage(
                scan_id, repo_dir, target, config, stage_by_name[StageName.DEPENDENCIES], on_stage, emit, errors
            )
        else:
            for name in (StageName.CLONING, StageName.STATIC_ANALYSIS, StageName.SECRETS, StageName.DEPENDENCIES):
                _mark(stage_by_name[name], StageStatus.SKIPPED, on_stage)

        _run_tool_description_stage(
            scan_id, target_type, target, repo_dir, config, stage_by_name[StageName.TOOL_DESCRIPTION_CHECK], on_stage, emit, errors
        )

        _mark(stage_by_name[StageName.AGGREGATING], StageStatus.RUNNING, on_stage)
        emit([not_tested_placeholder(scan_id)])
        scan.score = compute_score(scan.findings)
        scan.status = ScanStatus.FAILED if len(errors) == len(scan.stages) else ScanStatus.COMPLETED
        scan.completed_at = datetime.now(UTC)
        _mark(stage_by_name[StageName.AGGREGATING], StageStatus.DONE, on_stage)
        return scan
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _run_clone_stage(
    github_url: str, workdir: str, config: PipelineConfig, stage: ScanStage, on_stage: OnStage, errors: list[str]
) -> str:
    _mark(stage, StageStatus.RUNNING, on_stage)
    repo_dir = f"{workdir}/repo"
    clone_url = github_url
    if config.github_token and github_url.startswith("https://github.com/"):
        clone_url = github_url.replace("https://github.com/", f"https://x-access-token:{config.github_token}@github.com/")
    try:
        subprocess.run(
            ["git", "clone", "--depth", str(config.clone_depth), clone_url, repo_dir],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        if clone_url != github_url:
            # git writes the clone URL verbatim into .git/config — if it
            # carried our token, that token is now sitting on disk inside
            # the very directory every scanner tool (trufflehog, gitleaks,
            # semgrep...) is about to scan. Confirmed live: this shipped an
            # actual verified, highly-privileged Aevrin GitHub token back to
            # users as a "critical finding" on their own scan results.
            # Strip it immediately — the token was only ever needed for the
            # clone transport itself, not for anything scanned afterward.
            subprocess.run(
                ["git", "-C", repo_dir, "remote", "set-url", "origin", github_url],
                capture_output=True, text=True, timeout=10, check=True,
            )
        _mark(stage, StageStatus.DONE, on_stage)
        return repo_dir
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        msg = f"clone failed: {exc}"
        errors.append(msg)
        _mark(stage, StageStatus.FAILED, on_stage, error=msg)
        raise PipelineError(msg) from exc


def _normalize_paths(findings: list[Finding], root: str) -> list[Finding]:
    """Strips `root` (the real host directory a tool just scanned) from any
    absolute file_path it reported. Docker-mode tools report paths relative
    to the fixed /src mount already (or get fixed up by paths.relative_to_mount);
    subprocess-mode tools run with cwd=root and *mostly* report relative
    paths too, but at least one (osv-scanner, confirmed live) canonicalizes
    to an absolute path regardless of the "." it was given — this is the
    single place that catches any absolute path leak, in either mode."""
    root_prefix = root.rstrip("/") + "/"
    for f in findings:
        path = f.location.file_path
        if not path:
            continue
        path = path.removeprefix(root_prefix)
        path = path.removeprefix("./")  # e.g. bandit run with "-r ." reports "./app.py"
        f.location.file_path = path
    return findings


def _run_static_analysis_stage(
    scan_id: UUID, repo_dir: str, stage: ScanStage, on_stage: OnStage, emit: OnFindings, errors: list[str]
) -> None:
    _mark(stage, StageStatus.RUNNING, on_stage)
    tool_errors: list[str] = []
    for label, adapter in (("semgrep", SemgrepAdapter()), ("bandit", BanditAdapter())):
        findings, error = _run_isolated(label, lambda a=adapter: a.run(scan_id, repo_dir))  # type: ignore[misc]
        emit(_normalize_paths(findings, repo_dir))
        if error:
            tool_errors.append(error)
    _finish_stage(stage, tool_errors, on_stage, errors)


def _run_secrets_stage(
    scan_id: UUID, repo_dir: str, stage: ScanStage, on_stage: OnStage, emit: OnFindings, errors: list[str]
) -> None:
    _mark(stage, StageStatus.RUNNING, on_stage)
    tool_errors: list[str] = []
    for label, adapter in (("gitleaks", GitleaksAdapter()), ("trufflehog", TruffleHogAdapter())):
        findings, error = _run_isolated(label, lambda a=adapter: a.run(scan_id, repo_dir))  # type: ignore[misc]
        emit(_normalize_paths(findings, repo_dir))
        if error:
            tool_errors.append(error)
    _finish_stage(stage, tool_errors, on_stage, errors)


def _run_dependencies_stage(
    scan_id: UUID,
    repo_dir: str,
    github_url: str,
    config: PipelineConfig,
    stage: ScanStage,
    on_stage: OnStage,
    emit: OnFindings,
    errors: list[str],
) -> None:
    _mark(stage, StageStatus.RUNNING, on_stage)
    tool_errors: list[str] = []
    for label, adapter in (("osv-scanner", OsvScannerAdapter()), ("trivy", TrivyAdapter())):
        findings, error = _run_isolated(label, lambda a=adapter: a.run(scan_id, repo_dir))  # type: ignore[misc]
        emit(_normalize_paths(findings, repo_dir))
        if error:
            tool_errors.append(error)

    if config.github_token and github_url.startswith("https://github.com/"):
        owner_repo = github_url.removeprefix("https://github.com/").removesuffix(".git")
        scorecard = ScorecardAdapter(github_repo=owner_repo, github_token=config.github_token)
        findings, error = _run_isolated("openssf-scorecard", lambda: scorecard.run(scan_id, repo_dir))
        emit(findings)
        if error:
            tool_errors.append(error)
    elif not config.github_token:
        tool_errors.append("openssf-scorecard: skipped, no GITHUB_TOKEN configured")
    else:
        tool_errors.append("openssf-scorecard: skipped, target is not a github.com repo URL")

    _finish_stage(stage, tool_errors, on_stage, errors)


def _run_tool_description_stage(
    scan_id: UUID,
    target_type: TargetType,
    target: str,
    repo_dir: str | None,
    config: PipelineConfig,
    stage: ScanStage,
    on_stage: OnStage,
    emit: OnFindings,
    errors: list[str],
) -> None:
    _mark(stage, StageStatus.RUNNING, on_stage)
    tool_errors: list[str] = []

    mcp_entries = _discover_mcp_entries(target_type, target, repo_dir)
    if not mcp_entries:
        tool_errors.append("no MCP server entrypoint discovered — tool description checks skipped")
        _finish_stage(stage, tool_errors, on_stage, errors)
        return

    config_dir = tempfile.mkdtemp(prefix="aevrin-mcpcfg-")
    try:
        with open(f"{config_dir}/mcp.json", "w") as f:
            f.write(build_mcp_config(mcp_entries))

        findings, error = _run_isolated("mcp-shield", lambda: McpShieldAdapter().run(scan_id, config_dir))
        emit(findings)
        if error:
            tool_errors.append(error)

        signatures: list[PinnedSignature] = []
        try:
            for result in McpScanAdapter().inspect_signatures(config_dir):
                if result.signature is not None:
                    signatures.append(PinnedSignature(result.server_name, hash_signature(result.signature)))
        except ToolExecutionError as exc:
            tool_errors.append(f"mcp-scan: {exc}")
            try:
                for result in McpContextProtectorAdapter().inspect_signatures(config_dir):
                    if result.signature is not None:
                        signatures.append(PinnedSignature(result.server_name, hash_signature(result.signature)))
            except ToolExecutionError as exc2:
                tool_errors.append(f"mcp-context-protector (fallback): {exc2}")

        config.computed_signatures = [(s.server_name, s.signature_hash) for s in signatures]
        previous = [PinnedSignature(name, h) for name, h in config.previous_signatures.items()]
        emit(diff_signatures(scan_id, McpScanAdapter.tool, previous, signatures))

        for entry in mcp_entries.values():
            transport = TransportInfo(
                url=entry.get("url"),
                has_auth_header=bool(entry.get("headers")),
                has_api_key_env=any("key" in k.lower() or "token" in k.lower() for k in (entry.get("env") or {})),
            )
            emit(check_weak_auth(scan_id, transport))

        if repo_dir:
            emit(check_audit_logging_presence(scan_id, repo_dir))
    finally:
        shutil.rmtree(config_dir, ignore_errors=True)

    _finish_stage(stage, tool_errors, on_stage, errors)


def _discover_mcp_entries(
    target_type: TargetType, target: str, repo_dir: str | None
) -> dict[str, dict[str, Any]]:
    """Best-effort MCP server entrypoint discovery. Live-server targets are
    trivial (the target IS the entrypoint). Repo targets look for a
    committed .mcp/*.json or claude_desktop_config.json; a repo without one
    checked in yields no entries (see the tool_errors message above)."""
    if target_type == TargetType.LIVE_MCP_SERVER:
        return {"target-server": {"url": target}}
    if target_type == TargetType.CONFIG_PASTE:
        import json

        try:
            parsed = json.loads(target)
            entries: dict[str, Any] = parsed.get("mcpServers", parsed)
            return entries
        except json.JSONDecodeError:
            return {}
    if repo_dir:
        import json
        import os

        for candidate in (".mcp/config.json", "claude_desktop_config.json", "mcp.json"):
            path = os.path.join(repo_dir, candidate)
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        parsed = json.load(f)
                    entries = parsed.get("mcpServers", parsed)
                    return entries
                except (OSError, json.JSONDecodeError):
                    continue
    return {}


def _finish_stage(stage: ScanStage, tool_errors: list[str], on_stage: OnStage, errors: list[str]) -> None:
    if tool_errors:
        errors.extend(tool_errors)
    # A stage is only FAILED if every tool in it failed; partial results still count as DONE.
    all_failed = len(tool_errors) > 0 and stage.name in _tools_per_stage_count and len(tool_errors) >= _tools_per_stage_count[stage.name]
    _mark(stage, StageStatus.FAILED if all_failed else StageStatus.DONE, on_stage, error="; ".join(tool_errors) or None)


_tools_per_stage_count = {
    StageName.STATIC_ANALYSIS: 2,
    StageName.SECRETS: 2,
    StageName.DEPENDENCIES: 3,
    StageName.TOOL_DESCRIPTION_CHECK: 1,
}
