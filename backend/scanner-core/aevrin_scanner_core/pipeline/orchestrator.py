"""The one pipeline both backend/api and backend/cli run; this is what keeps
findings from drifting into different vocabularies between the website, the
CLI, and the hook. Callers supply an `on_stage` callback for side effects
(DB writes for the web polling UI, terminal printing for the CLI) and get
back a fully-populated Scan.

GitHub-repo targets get the full tool set. Live-server and pasted-config
targets only get manifest-level checks (mcp-shield/SDK inspection/manifest rules)
per Section 6; cloning/static-analysis/secrets/dependency stages are marked
SKIPPED, not silently absent.
"""

from __future__ import annotations

import re
import shutil

# This module invokes Git with structured argv and shell=False.
import subprocess  # nosec B404
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from ..adapters import (
    BanditAdapter,
    GitleaksAdapter,
    McpShieldAdapter,
    OsvScannerAdapter,
    ScorecardAdapter,
    SemgrepAdapter,
    TrivyAdapter,
    TruffleHogAdapter,
)
from ..adapters.mcp_shield import build_mcp_config
from ..analysis.manifest_rules import (
    ToolDescriptor,
    TransportInfo,
    check_audit_logging_presence,
    check_dangerous_launch_command,
    check_excessive_agency,
    check_weak_auth,
)
from ..analysis.mcp_detection import detect_mcp_server, discover_tools
from ..analysis.remote_mcp import inspect_remote_signatures
from ..analysis.rug_pull import PinnedSignature, diff_signatures
from ..classification.scoring import compute_score
from ..execution.network_safety import public_https_url_error
from ..execution.runner import ToolExecutionError, sanitized_subprocess_env
from ..models import (
    Finding,
    Scan,
    ScanStage,
    ScanStatus,
    StageName,
    StageStatus,
    TargetType,
    ToolName,
)
from .not_tested import not_tested_placeholder
from .postprocess import postprocess_findings

OnStage = Callable[[ScanStage], None]
OnFindings = Callable[[list[Finding]], None]


@dataclass
class PipelineConfig:
    github_token: str | None = None
    clone_depth: int = 50
    # {server_name: signature_hash} from the last scan of this exact target;
    # empty on first scan, populated by the caller from persisted state.
    previous_signatures: dict[str, str] = field(default_factory=dict)
    # (server_name, signature_hash) pairs computed this run, caller persists
    # these after the pipeline returns so the *next* scan can diff against them.
    computed_signatures: list[tuple[str, str]] = field(default_factory=list)


class PipelineError(Exception):
    pass


def _mark(stage: ScanStage, status: StageStatus, on_stage: OnStage, error: str | None = None) -> None:
    stage.status = status
    stage.error = error
    if status == StageStatus.RUNNING:
        stage.started_at = datetime.now(timezone.utc)
    elif status in (StageStatus.DONE, StageStatus.FAILED, StageStatus.SKIPPED):
        stage.finished_at = datetime.now(timezone.utc)
    on_stage(stage)


def _run_isolated(label: str, fn: Callable[[], list[Finding]]) -> tuple[list[Finding], str | None]:
    try:
        return fn(), None
    except ToolExecutionError as exc:
        return [], f"{label}: {exc}"
    except Exception as exc:  # noqa: BLE001 - a crashing adapter must never take down the scan
        return [], f"{label}: unexpected error: {exc}"


# Stages whose "zero findings" claim is only meaningful if at least one real
# tool in the category actually ran. TOOL_DESCRIPTION_CHECK is deliberately
# excluded; its most common "failure" (no MCP entrypoint discovered) is a
# legitimate, expected outcome for most repos, not a broken tool.
_CORE_STAGES = (StageName.STATIC_ANALYSIS, StageName.SECRETS, StageName.DEPENDENCIES)


def _run_tool_group(
    scan_id: UUID,
    repo_dir: str,
    tools: tuple[tuple[str, Any], ...],
    emit: OnFindings,
) -> tuple[list[str], int]:
    """Runs each (label, adapter) pair, normalizing and emitting findings.
    Returns (tool_errors, succeeded_count); succeeded_count is how many of
    these tools actually executed, independent of whether they found
    anything, so callers can tell "ran clean" apart from "never ran"."""
    tool_errors: list[str] = []
    succeeded = 0
    for label, adapter in tools:
        findings, error = _run_isolated(label, lambda a=adapter: a.run(scan_id, repo_dir))  # type: ignore[misc]
        emit(_normalize_paths(findings, repo_dir))
        if error:
            tool_errors.append(error)
        else:
            succeeded += 1
    return tool_errors, succeeded


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
    stage_reliable: dict[StageName, bool] = {}
    try:
        repo_dir = None
        if target_type == TargetType.GITHUB_REPO:
            repo_dir = _run_clone_stage(target, workdir, config, stage_by_name[StageName.CLONING], on_stage, errors)
            stage_reliable[StageName.STATIC_ANALYSIS] = _run_static_analysis_stage(
                scan_id, repo_dir, stage_by_name[StageName.STATIC_ANALYSIS], on_stage, emit, errors
            )
            stage_reliable[StageName.SECRETS] = _run_secrets_stage(
                scan_id, repo_dir, stage_by_name[StageName.SECRETS], on_stage, emit, errors
            )
            stage_reliable[StageName.DEPENDENCIES] = _run_dependencies_stage(
                scan_id, repo_dir, target, config, stage_by_name[StageName.DEPENDENCIES], on_stage, emit, errors
            )
        elif target_type == TargetType.LOCAL_PATH:
            # CLI scanning the user's own machine: nothing to clone, the
            # target IS the directory to scan. Not a git URL, so Scorecard
            # (github-repo-only) is skipped inside _run_dependencies_stage.
            repo_dir = target
            _mark(stage_by_name[StageName.CLONING], StageStatus.SKIPPED, on_stage)
            stage_reliable[StageName.STATIC_ANALYSIS] = _run_static_analysis_stage(
                scan_id, repo_dir, stage_by_name[StageName.STATIC_ANALYSIS], on_stage, emit, errors
            )
            stage_reliable[StageName.SECRETS] = _run_secrets_stage(
                scan_id, repo_dir, stage_by_name[StageName.SECRETS], on_stage, emit, errors
            )
            stage_reliable[StageName.DEPENDENCIES] = _run_dependencies_stage(
                scan_id, repo_dir, target, config, stage_by_name[StageName.DEPENDENCIES], on_stage, emit, errors
            )
        else:
            for name in (StageName.CLONING, StageName.STATIC_ANALYSIS, StageName.SECRETS, StageName.DEPENDENCIES):
                _mark(stage_by_name[name], StageStatus.SKIPPED, on_stage)

        # A live-server URL or a pasted mcp.json *is* MCP by construction;
        # only a repo/local-path target is actually ambiguous.
        if repo_dir and target_type in (TargetType.GITHUB_REPO, TargetType.LOCAL_PATH):
            detection = detect_mcp_server(repo_dir)
            scan.mcp_detected = detection.is_mcp_server
            scan.mcp_detection_confidence = detection.confidence
            scan.mcp_detection_evidence = [f"{s.kind}: {s.detail}" for s in detection.signals[:10]]
        else:
            scan.mcp_detected = True
            scan.mcp_detection_confidence = "high"
            scan.mcp_detection_evidence = ["target_type: the target is an MCP server by construction"]

        _run_tool_description_stage(
            scan, target_type, target, repo_dir, config, stage_by_name[StageName.TOOL_DESCRIPTION_CHECK], on_stage, emit, errors
        )

        _mark(stage_by_name[StageName.AGGREGATING], StageStatus.RUNNING, on_stage)
        emit([not_tested_placeholder(scan_id)])
        # Fixture-path exclusion, cross-scanner dedup, root-cause grouping,
        # dependency dev/prod scope, and EPSS/CISA-KEV enrichment all need
        # the *complete* finding set (some inherently span tools/stages), so
        # this only happens once here; after every stage has emitted, right
        # before compute_score. See postprocess.py.
        scan.findings = postprocess_findings(scan.findings, repo_dir)
        scan.score = compute_score(scan.findings)
        # stage_reliable only has entries for stages that were actually
        # attempted (GITHUB_REPO/LOCAL_PATH targets), a stage absent from it
        # (e.g. skipped entirely for a live-server/config-paste target) was
        # never claimed to have run, so it can't be "unreliable".
        scan.unreliable_stages = [name for name in _CORE_STAGES if stage_reliable.get(name) is False]
        scan.status = ScanStatus.INCOMPLETE if scan.unreliable_stages else ScanStatus.COMPLETED
        scan.completed_at = datetime.now(timezone.utc)
        _mark(stage_by_name[StageName.AGGREGATING], StageStatus.DONE, on_stage)
        return scan
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


_CLONE_URL_TOKEN_RE = re.compile(r"://x-access-token:[^@\s]+@")


def _redact_token(text: str, token: str | None) -> str:
    if token:
        text = text.replace(token, "***")
    return _CLONE_URL_TOKEN_RE.sub("://x-access-token:***@", text)


def _run_clone_stage(
    github_url: str, workdir: str, config: PipelineConfig, stage: ScanStage, on_stage: OnStage, errors: list[str]
) -> str:
    _mark(stage, StageStatus.RUNNING, on_stage)
    repo_dir = f"{workdir}/repo"
    clone_url = github_url
    if config.github_token and github_url.startswith("https://github.com/"):
        clone_url = github_url.replace("https://github.com/", f"https://x-access-token:{config.github_token}@github.com/")
    try:
        # Fixed Git executable and structured argv; clone_url is one argument.
        subprocess.run(  # nosec B603 B607
            ["git", "clone", "--depth", str(config.clone_depth), clone_url, repo_dir],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
            env=sanitized_subprocess_env(),
        )
        if clone_url != github_url:
            # git writes the clone URL verbatim into .git/config, if it
            # carried our token, that token is now sitting on disk inside
            # the very directory every scanner tool (trufflehog, gitleaks,
            # semgrep...) is about to scan. Confirmed live: this shipped an
            # actual verified, highly-privileged Aevrin GitHub token back to
            # users as a "critical finding" on their own scan results.
            # Strip it immediately: the token was only ever needed for the
            # clone transport itself, not for anything scanned afterward.
            # Fixed Git executable and structured argv.
            subprocess.run(  # nosec B603 B607
                ["git", "-C", repo_dir, "remote", "set-url", "origin", github_url],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
                env=sanitized_subprocess_env(),
            )
        _mark(stage, StageStatus.DONE, on_stage)
        return repo_dir
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        # str(exc) on a CalledProcessError/TimeoutExpired includes the full
        # argv, which is clone_url, carrying our token in plaintext if one
        # was used. Confirmed live: this shipped that token straight to the
        # user as a scan-stage error message. Redact before it ever reaches
        # errors/on_stage (both get persisted and rendered back to the user).
        msg = f"clone failed: {_redact_token(str(exc), config.github_token)}"
        errors.append(msg)
        _mark(stage, StageStatus.FAILED, on_stage, error=msg)
        raise PipelineError(msg) from exc


def _normalize_paths(findings: list[Finding], root: str) -> list[Finding]:
    """Strips `root` (the real host directory a tool just scanned) from any
    absolute file_path it reported. Docker-mode tools report paths relative
    to the fixed /src mount already (or get fixed up by paths.relative_to_mount);
    subprocess-mode tools run with cwd=root and *mostly* report relative
    paths too, but at least one (osv-scanner, confirmed live) canonicalizes
    to an absolute path regardless of the "." it was given; this is the
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
) -> bool:
    """Returns True iff at least one tool in this category actually ran."""
    _mark(stage, StageStatus.RUNNING, on_stage)
    tool_errors, succeeded = _run_tool_group(
        scan_id, repo_dir, (("semgrep", SemgrepAdapter()), ("bandit", BanditAdapter())), emit
    )
    _finish_stage(stage, tool_errors, on_stage, errors)
    return succeeded > 0


def _run_secrets_stage(
    scan_id: UUID, repo_dir: str, stage: ScanStage, on_stage: OnStage, emit: OnFindings, errors: list[str]
) -> bool:
    """Returns True iff at least one tool in this category actually ran."""
    _mark(stage, StageStatus.RUNNING, on_stage)
    tool_errors, succeeded = _run_tool_group(
        scan_id, repo_dir, (("gitleaks", GitleaksAdapter()), ("trufflehog", TruffleHogAdapter())), emit
    )
    _finish_stage(stage, tool_errors, on_stage, errors)
    return succeeded > 0


def _run_dependencies_stage(
    scan_id: UUID,
    repo_dir: str,
    github_url: str,
    config: PipelineConfig,
    stage: ScanStage,
    on_stage: OnStage,
    emit: OnFindings,
    errors: list[str],
) -> bool:
    """Returns True iff at least one tool in this category actually ran.
    openssf-scorecard is excluded from that check; it's opt-in (requires a
    GITHUB_TOKEN) and its absence is expected, not a sign osv-scanner/trivy
    are unreliable."""
    _mark(stage, StageStatus.RUNNING, on_stage)
    tool_errors, succeeded = _run_tool_group(
        scan_id, repo_dir, (("osv-scanner", OsvScannerAdapter()), ("trivy", TrivyAdapter())), emit
    )

    notices: list[str] = []
    if config.github_token and github_url.startswith("https://github.com/"):
        owner_repo = github_url.removeprefix("https://github.com/").removesuffix(".git")
        scorecard = ScorecardAdapter(github_repo=owner_repo, github_token=config.github_token)
        findings, error = _run_isolated("openssf-scorecard", lambda: scorecard.run(scan_id, repo_dir))
        emit(findings)
        # A scorecard that was asked to run and then broke IS a failure; only
        # never being asked is a notice.
        if error:
            tool_errors.append(error)
    elif not config.github_token:
        notices.append("openssf-scorecard: skipped, no GITHUB_TOKEN configured")
    else:
        notices.append("openssf-scorecard: skipped, target is not a github.com repo URL")

    _finish_stage(stage, tool_errors, on_stage, errors, notices=tuple(notices))
    return succeeded > 0


def _partition_safe_remote_entries(
    mcp_entries: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Splits MCP entries into ones safe to probe and the reasons the rest are not.

    Tool-description scanners connect to remote servers, and some upstream tools
    will execute stdio commands straight from the configuration. Never execute
    those untrusted commands in the API/CLI scanner context, and never let a
    submitted URL reach loopback, metadata, or private networks.
    """
    safe: dict[str, dict[str, Any]] = {}
    limitations: list[str] = []
    for name, entry in mcp_entries.items():
        if not isinstance(entry, dict):
            limitations.append(f"{name}: invalid MCP entry")
            continue
        url = entry.get("url")
        if not isinstance(url, str):
            limitations.append(f"{name}: stdio command not executed for safety")
            continue
        url_error = public_https_url_error(url)
        if url_error:
            limitations.append(f"{name}: {url_error}")
            continue
        safe[name] = entry
    return safe, limitations


def _probe_remote_servers(
    scan_id: UUID,
    mcp_entries: dict[str, dict[str, Any]],
    repo_dir: str | None,
    config: PipelineConfig,
    emit: OnFindings,
    tool_errors: list[str],
) -> bool:
    """Runs every runtime check against the safe entries, in a throwaway config
    dir. Returns whether MCP-Shield itself ran, which is what decides the stage
    verdict; signature pinning can be unavailable while description coverage is
    still real.
    """
    config_dir = tempfile.mkdtemp(prefix="aevrin-mcpcfg-")
    try:
        with open(f"{config_dir}/mcp.json", "w") as f:
            f.write(build_mcp_config(mcp_entries))

        findings, error = _run_isolated("mcp-shield", lambda: McpShieldAdapter().run(scan_id, config_dir))
        emit(findings)
        if error:
            tool_errors.append(error)
        mcp_shield_succeeded = error is None

        signatures: list[PinnedSignature] = []
        try:
            signatures = [
                PinnedSignature(name, signature)
                for name, signature in inspect_remote_signatures(mcp_entries)
            ]
        except Exception as exc:  # noqa: BLE001 - remote protocol errors are isolated
            tool_errors.append(f"MCP signature inspection: {type(exc).__name__}: {exc}")

        config.computed_signatures = [(s.server_name, s.signature_hash) for s in signatures]
        previous = [PinnedSignature(name, h) for name, h in config.previous_signatures.items()]
        emit(diff_signatures(scan_id, ToolName.MCP_SCAN, previous, signatures))

        for entry in mcp_entries.values():
            transport = TransportInfo(
                url=entry.get("url"),
                has_auth_header=bool(entry.get("headers")),
                has_api_key_env=any("key" in k.lower() or "token" in k.lower() for k in (entry.get("env") or {})),
            )
            emit(check_weak_auth(scan_id, transport))

        if repo_dir:
            emit(check_audit_logging_presence(scan_id, repo_dir))
        return mcp_shield_succeeded
    finally:
        shutil.rmtree(config_dir, ignore_errors=True)


def _run_source_mcp_analysis(
    scan: Scan, repo_dir: str, emit: OnFindings
) -> bool:
    """MCP-specific analysis of a repository that *is* an MCP server.

    This is the half of the pipeline that used to be missing. A server's own
    repository has no reason to commit a client config pointing at itself, so
    `_discover_mcp_entries` finds nothing there and the whole MCP stage was
    skipped -- meaning the most important target in the product, an actual MCP
    server, received generic code-security analysis and no MCP analysis at all.

    Everything here reads declarations out of source. Nothing is imported,
    executed, or connected to, which is what makes it safe to run against a
    repository nobody has vetted. The cost of that restraint is real and is
    reported rather than hidden: a tool registered through indirection this
    cannot parse is a tool that does not appear below.

    Returns whether any MCP surface was actually read, so the caller can tell
    "checked, found nothing" apart from "could not check".
    """
    tools = discover_tools(repo_dir)
    scan.mcp_tools_declared = [tool.name for tool in tools]
    if not tools:
        return False

    # The same manifest rule the runtime path uses, fed from source instead of
    # from a live handshake. One rule, one vocabulary, two sources of tools.
    emit(
        check_excessive_agency(
            scan.id, [ToolDescriptor(tool.name, tool.description) for tool in tools]
        )
    )
    # Audit logging is a property of the code, so it was always answerable for
    # a repository; it simply never got the chance to run.
    emit(check_audit_logging_presence(scan.id, repo_dir))
    return True


def _run_tool_description_stage(
    scan: Scan,
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
    scan_id = scan.id
    tool_errors: list[str] = []

    # Source-derived MCP analysis runs first and independently of any runtime
    # probe, because it is the only MCP check available for the common case of
    # a repository that ships a server rather than a config that consumes one.
    source_analysis_ran = False
    if repo_dir and scan.mcp_detected:
        source_analysis_ran = _run_source_mcp_analysis(scan, repo_dir, emit)

    mcp_entries = _discover_mcp_entries(target_type, target, repo_dir)
    if not mcp_entries:
        if source_analysis_ran:
            # The MCP surface *was* examined, just statically. Marking this
            # DONE rather than SKIPPED matters: SKIPPED feeds the "coverage
            # incomplete" signal, and claiming no coverage when a repository's
            # tools were read and checked would understate a real result.
            _mark(
                stage,
                StageStatus.DONE,
                on_stage,
                error=(
                    f"Tool descriptions were read from source ({len(scan.mcp_tools_declared)} "
                    "declared). Runtime probing was not applicable: no reachable endpoint "
                    "is declared in this repository."
                ),
            )
            return
        # This is an applicability limitation, not a scanner crash. Source
        # repositories commonly contain an MCP SDK without committing a
        # runnable client configuration, and executing arbitrary project code
        # merely to enumerate tools would violate the scanner's safety model.
        _mark(
            stage,
            StageStatus.SKIPPED,
            on_stage,
            error=(
                "No safe MCP server entrypoint was discovered. Runtime tool-description "
                "checks were not applicable to this source scan."
            ),
        )
        return

    # Static inspection of what each entry would execute. This deliberately
    # runs BEFORE the two "nothing safe to probe" early returns below: it
    # reads the declared command, never runs it, so it is exactly the check
    # that must survive when every runtime probe is refused. A stdio-only
    # pasted config takes that skip path, which previously meant it produced
    # no findings whatsoever, a server launching `sh -c "curl …|sh"` scored
    # a clean 100/100.
    emit(check_dangerous_launch_command(scan_id, mcp_entries))

    safe_remote_entries, limitations = _partition_safe_remote_entries(mcp_entries)

    if not safe_remote_entries:
        _mark(
            stage,
            # Same distinction as above: if the repository's own tools were
            # read from source, this category was covered, and only the
            # runtime probe was declined.
            StageStatus.DONE if source_analysis_ran else StageStatus.SKIPPED,
            on_stage,
            error=(
                "Runtime tool-description checks were not run because no safe public HTTPS "
                "MCP endpoint was available. Aevrin never executes submitted stdio commands. "
                + "; ".join(limitations)
            ),
        )
        return
    # Only the filtered set is ever probed; the unfiltered `mcp_entries` is
    # deliberately not reused past this point.
    mcp_shield_succeeded = _probe_remote_servers(
        scan_id, safe_remote_entries, repo_dir, config, emit, tool_errors
    )

    if limitations:
        tool_errors.extend(limitations)
    if tool_errors:
        errors.extend(tool_errors)
    # Signature pinning can be unavailable while MCP-Shield still provided
    # real description coverage. Only fail the stage when the primary runtime
    # description check itself did not run.
    _mark(
        stage,
        StageStatus.DONE if mcp_shield_succeeded else StageStatus.FAILED,
        on_stage,
        error="; ".join(tool_errors) or None,
    )


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


def _finish_stage(
    stage: ScanStage,
    tool_errors: list[str],
    on_stage: OnStage,
    errors: list[str],
    notices: tuple[str, ...] = (),
) -> None:
    """`notices` are tools that were never going to run here -- opt-in, or not
    applicable to this target. They are reported, because a silently absent
    check is exactly what this scanner refuses to do, but they are not
    failures: they do not reach the scan-level error list and they do not
    count toward the threshold below.

    Keeping them in `tool_errors` made "openssf-scorecard: skipped, no
    GITHUB_TOKEN configured" read as a broken tool, and worse, made the
    dependencies stage's verdict depend on whether that skip happened to be
    present to pad the count.
    """
    if tool_errors:
        errors.extend(tool_errors)
    # A stage is only FAILED if every tool in it failed; partial results still count as DONE.
    all_failed = len(tool_errors) > 0 and stage.name in _tools_per_stage_count and len(tool_errors) >= _tools_per_stage_count[stage.name]
    message = "; ".join([*tool_errors, *notices]) or None
    _mark(stage, StageStatus.FAILED if all_failed else StageStatus.DONE, on_stage, error=message)


# How many tools have to fail before the stage itself counts as failed. Only
# the tools that decide whether the category was actually covered: dependencies
# is 2 (osv-scanner, trivy), NOT 3. Counting openssf-scorecard here contradicted
# _run_dependencies_stage, which already excludes it from that judgement, and
# meant both real dependency scanners could fail while the stage reported
# success -- green, with no dependency scanning having happened at all.
_tools_per_stage_count = {
    StageName.STATIC_ANALYSIS: 2,
    StageName.SECRETS: 2,
    StageName.DEPENDENCIES: 2,
    StageName.TOOL_DESCRIPTION_CHECK: 1,
}
