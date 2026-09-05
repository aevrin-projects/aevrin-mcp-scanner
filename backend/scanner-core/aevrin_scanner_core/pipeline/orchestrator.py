"""The one pipeline both backend/api and backend/cli run.

This is what keeps findings from drifting into different vocabularies
between the website, the CLI, and the hook. Callers supply an `on_stage`
callback for side effects (DB writes for the web polling UI, terminal
printing for the CLI) and get back a fully-populated `Scan`.

The shape of the pipeline follows what Aevrin is: an MCP security scanner.
Tool discovery comes first, because everything downstream is about tools;
the rule engine runs against those tools whether they were read from source
or from a live handshake; and the two remaining external scanners answer
narrow, MCP-relevant questions (is a credential committed here, does the
dependency tree carry a published advisory) rather than auditing the
repository at large.

A target with no readable tools is graded incomplete, never clean. That is
the single most important behaviour in this file: an empty finding list
from a server whose tools could not be enumerated looks exactly like a
perfect result, and saying so out loud is the difference between a security
product and a green badge.
"""

from __future__ import annotations

import json
import os
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

from ..adapters import McpBehaviorAdapter, OsvScannerAdapter, TruffleHogAdapter
from ..analysis.capability_map import attribute_findings_to_tools
from ..analysis.declared_vs_observed import flag_undeclared_capabilities
from ..analysis.discovery import discover_tools
from ..analysis.manifest_rules import (
    TransportInfo,
    check_audit_logging_presence,
    check_dangerous_launch_command,
    check_weak_auth,
)
from ..analysis.mcp_detection import detect_mcp_server
from ..analysis.remote_mcp import inspect_remote_servers
from ..analysis.rug_pull import PinnedSignature, diff_signatures, hash_signature
from ..execution.network_safety import public_https_url_error
from ..execution.runner import ToolExecutionError, sanitized_subprocess_env
from ..mcp.risk import grade_scan
from ..mcp.rules import check_unenumerable_tools, run_rules
from ..mcp.supply_chain import run_supply_chain_rules
from ..mcp.tools import McpTool, capability_summary, merge_capability_summaries
from ..models import (
    Finding,
    Scan,
    ScanStage,
    ScanStatus,
    StageName,
    StageStatus,
    TargetType,
)
from .not_tested import not_tested_placeholder
from .postprocess import postprocess_findings

OnStage = Callable[[ScanStage], None]
OnFindings = Callable[[list[Finding]], None]


@dataclass
class PipelineConfig:
    github_token: str | None = None
    clone_depth: int = 50
    # {key: signature_hash} from the last scan of this exact target; empty on
    # first scan, populated by the caller from persisted state. Two disjoint
    # keyspaces share this one dict on purpose (see
    # docs/features/MCP_SCANNING.md): a live probe's key is the server name
    # straight out of the MCP config, and a source repository's key is
    # `tool:{tool_name}`. The prefix is what keeps a same-named live server
    # and declared tool from colliding, rather than a second table for what
    # is underneath the same "did this target's surface change" question.
    previous_signatures: dict[str, str] = field(default_factory=dict)
    # (key, signature_hash) pairs computed this run, same keyspace as above.
    # Extended, never reassigned: one target can exercise both the live probe
    # and the source path in a single scan.
    computed_signatures: list[tuple[str, str]] = field(default_factory=list)


class PipelineError(Exception):
    pass


def _mark(
    stage: ScanStage, status: StageStatus, on_stage: OnStage, error: str | None = None
) -> None:
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


# Stages whose "zero findings" claim is only meaningful if the check behind
# it actually ran. MCP_RULES is not here: it runs in-process and cannot fail
# to execute, and its own coverage question ("were there any tools to check")
# is answered by `tools_discovered` on the grade instead.
_CORE_STAGES = (StageName.SECRETS, StageName.DEPENDENCIES)


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
        repo_dir: str | None = None
        if target_type == TargetType.GITHUB_REPO:
            repo_dir = _run_clone_stage(
                target, workdir, config, stage_by_name[StageName.CLONING], on_stage, errors
            )
        elif target_type == TargetType.LOCAL_PATH:
            # The CLI scanning the user's own machine: nothing to clone, the
            # target IS the directory to scan.
            repo_dir = target
            _mark(stage_by_name[StageName.CLONING], StageStatus.SKIPPED, on_stage)
        else:
            _mark(stage_by_name[StageName.CLONING], StageStatus.SKIPPED, on_stage)

        tools = _run_discovery_stage(
            scan, target_type, target, repo_dir, stage_by_name[StageName.DISCOVERY], on_stage
        )

        mcp_entries = _discover_mcp_entries(target_type, target, repo_dir)
        tools = _run_mcp_rules_stage(
            scan,
            tools,
            mcp_entries,
            repo_dir,
            config,
            stage_by_name[StageName.MCP_RULES],
            on_stage,
            emit,
            errors,
        )

        _run_behavior_stage(
            scan, repo_dir, tools, stage_by_name[StageName.MCP_BEHAVIOR], on_stage, emit, errors
        )

        if repo_dir:
            stage_reliable[StageName.SECRETS] = _run_secrets_stage(
                scan_id, repo_dir, stage_by_name[StageName.SECRETS], on_stage, emit, errors
            )
            stage_reliable[StageName.DEPENDENCIES] = _run_dependencies_stage(
                scan_id, repo_dir, stage_by_name[StageName.DEPENDENCIES], on_stage, emit, errors
            )
        else:
            for name in (StageName.SECRETS, StageName.DEPENDENCIES):
                _mark(
                    stage_by_name[name],
                    StageStatus.SKIPPED,
                    on_stage,
                    error="No source repository is available for this target type.",
                )

        _mark(stage_by_name[StageName.AGGREGATING], StageStatus.RUNNING, on_stage)
        emit([not_tested_placeholder(scan_id)])
        scan.findings = postprocess_findings(scan_id, scan.findings, repo_dir)

        scan.unreliable_stages = [
            name for name in _CORE_STAGES if stage_reliable.get(name) is False
        ]
        grade = grade_scan(
            scan.findings,
            coverage_complete=not scan.unreliable_stages,
            tools_discovered=len(scan.mcp_tools_declared),
        )
        scan.risk_score = grade.risk_score
        scan.grade = grade.grade.value if grade.grade else None
        scan.status = ScanStatus.INCOMPLETE if grade.incomplete else ScanStatus.COMPLETED
        scan.completed_at = datetime.now(timezone.utc)
        _mark(stage_by_name[StageName.AGGREGATING], StageStatus.DONE, on_stage)
        return scan
    finally:
        # Never delete the caller's own directory on a LOCAL_PATH scan; only
        # the temporary workspace this function created.
        shutil.rmtree(workdir, ignore_errors=True)


# --------------------------------------------------------------------------
# Cloning

_CLONE_URL_TOKEN_RE = re.compile(r"://x-access-token:[^@\s]+@")


def _redact_token(text: str, token: str | None) -> str:
    if token:
        text = text.replace(token, "***")
    return _CLONE_URL_TOKEN_RE.sub("://x-access-token:***@", text)


def _run_clone_stage(
    github_url: str,
    workdir: str,
    config: PipelineConfig,
    stage: ScanStage,
    on_stage: OnStage,
    errors: list[str],
) -> str:
    _mark(stage, StageStatus.RUNNING, on_stage)
    repo_dir = f"{workdir}/repo"
    clone_url = github_url
    if config.github_token and github_url.startswith("https://github.com/"):
        clone_url = github_url.replace(
            "https://github.com/", f"https://x-access-token:{config.github_token}@github.com/"
        )
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
            # git writes the clone URL verbatim into .git/config; if it
            # carried our token, that token is now sitting on disk inside the
            # very directory the secret scanner is about to read. Confirmed
            # live: this once shipped a real, highly-privileged Aevrin GitHub
            # token back to users as a "critical finding" on their own scan.
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
        # str(exc) includes the full argv, which is clone_url, carrying our
        # token in plaintext if one was used. Redact before it reaches
        # errors/on_stage - both get persisted and rendered back to the user.
        message = f"clone failed: {_redact_token(str(exc), config.github_token)}"
        errors.append(message)
        _mark(stage, StageStatus.FAILED, on_stage, error=message)
        raise PipelineError(message) from exc


def _normalize_paths(findings: list[Finding], root: str) -> list[Finding]:
    """Strips `root` from any absolute file_path a tool reported.

    Docker-mode tools report paths relative to the fixed /src mount already;
    subprocess-mode tools run with cwd=root and mostly report relative paths
    too, but at least one (osv-scanner, confirmed live) canonicalizes to an
    absolute path regardless of the "." it was given. This is the single
    place that catches an absolute path leak in either mode.
    """
    root_prefix = root.rstrip("/") + "/"
    for finding in findings:
        path = finding.location.file_path
        if not path:
            continue
        finding.location.file_path = path.removeprefix(root_prefix).removeprefix("./")
    return findings


# --------------------------------------------------------------------------
# Discovery


def _run_discovery_stage(
    scan: Scan,
    target_type: TargetType,
    target: str,
    repo_dir: str | None,
    stage: ScanStage,
    on_stage: OnStage,
) -> list[McpTool]:
    """Is this an MCP server, and what does it expose?

    Both halves land on the `Scan` here rather than being recomputed later:
    everything downstream reads `tools`, and `discover_tools` walks the whole
    repository to build it.
    """
    _mark(stage, StageStatus.RUNNING, on_stage)

    if repo_dir and target_type in (TargetType.GITHUB_REPO, TargetType.LOCAL_PATH):
        detection = detect_mcp_server(repo_dir)
        scan.mcp_detected = detection.is_mcp_server
        scan.mcp_detection_confidence = detection.confidence
        scan.mcp_detection_evidence = [f"{s.kind}: {s.detail}" for s in detection.signals[:10]]
        scan.mcp_components = [
            {
                "root": component.root,
                "confidence": component.confidence,
                "evidence": [f"{s.kind}: {s.detail}" for s in component.signals[:6]],
            }
            for component in detection.components
        ]
    else:
        # A live-server URL or a pasted mcp.json *is* MCP by construction.
        scan.mcp_detected = True
        scan.mcp_detection_confidence = "high"
        scan.mcp_detection_evidence = ["target_type: the target is an MCP server by construction"]

    tools: list[McpTool] = []
    if repo_dir and scan.mcp_detected:
        tools = discover_tools(repo_dir)

    scan.mcp_tools_declared = [tool.name for tool in tools]
    scan.mcp_capabilities = capability_summary(tools) if tools else None

    if not scan.mcp_detected:
        _mark(
            stage,
            StageStatus.DONE,
            on_stage,
            error=(
                "This repository does not look like an MCP server. Aevrin scans MCP servers "
                "and the agents that install them; it does not audit general source code, so "
                "there is nothing further for it to check here."
            ),
        )
        return tools

    _mark(
        stage,
        StageStatus.DONE,
        on_stage,
        error=(
            None
            if tools
            else (
                "No tool registrations could be read. Tools registered through indirection "
                "are not visible to static discovery, so this scan cannot describe the "
                "server's surface and will not grade it."
            )
        ),
    )
    return tools


# --------------------------------------------------------------------------
# The rule engine

_TOOL_SIGNATURE_PREFIX = "tool:"


def _run_mcp_rules_stage(
    scan: Scan,
    tools: list[McpTool],
    mcp_entries: dict[str, dict[str, Any]],
    repo_dir: str | None,
    config: PipelineConfig,
    stage: ScanStage,
    on_stage: OnStage,
    emit: OnFindings,
    errors: list[str],
) -> list[McpTool]:
    """The tool-definition rules, plus Aevrin's own launch/auth/logging rules.

    Returns the tool list the rest of the pipeline should use - a live
    handshake can add tools a repository never declared, and the behavior
    stage and the capability summary both need the union.
    """
    _mark(stage, StageStatus.RUNNING, on_stage)
    scan_id = scan.id
    notices: list[str] = []
    tool_errors: list[str] = []

    # Reading a config's launch command never runs it, which is exactly why
    # this has to happen before any of the "nothing safe to probe" exits
    # below: a stdio-only pasted config takes every one of them, and without
    # this it would produce no findings at all.
    if mcp_entries:
        emit(check_dangerous_launch_command(scan_id, mcp_entries))

    live_tools, live_notices, live_errors = _probe_live_servers(
        scan, mcp_entries, config, emit
    )
    notices.extend(live_notices)
    tool_errors.extend(live_errors)

    all_tools = _merge_tools(tools, live_tools)
    if live_tools:
        scan.mcp_tools_declared = [tool.name for tool in all_tools]
        scan.mcp_capabilities = merge_capability_summaries(
            scan.mcp_capabilities, capability_summary(live_tools)
        )

    if all_tools:
        emit(run_rules(scan_id, all_tools))
        emit(_diff_source_tool_signatures(scan_id, all_tools, config))

    if repo_dir:
        supply_chain_findings, _ = run_supply_chain_rules(scan_id, repo_dir)
        emit(supply_chain_findings)
        emit(check_audit_logging_presence(scan_id, repo_dir))

    if not all_tools:
        # AS-018: a confirmed MCP server whose surface could not be read. The
        # scan is about to be graded incomplete; this is the finding that says
        # why, so the report is not just an empty list beside a bare "?".
        if scan.mcp_detected:
            emit(check_unenumerable_tools(scan_id))
        notices.append(
            "No tools were available to check: none could be read from source, and no "
            "reachable endpoint was declared."
        )

    if tool_errors:
        errors.extend(tool_errors)
    message = "; ".join([*tool_errors, *notices]) or None
    _mark(stage, StageStatus.DONE, on_stage, error=message)
    return all_tools


def _merge_tools(source_tools: list[McpTool], live_tools: list[McpTool]) -> list[McpTool]:
    """Union by name, with the live definition winning.

    A live handshake reports what the server actually answers with today,
    which is a stronger claim than what its source appears to register - and
    is the half that would catch a server whose published code and running
    behaviour have diverged.
    """
    merged = {tool.name: tool for tool in source_tools}
    for tool in live_tools:
        merged[tool.name] = tool
    return sorted(merged.values(), key=lambda tool: tool.name)


def _diff_source_tool_signatures(
    scan_id: UUID, tools: list[McpTool], config: PipelineConfig
) -> list[Finding]:
    """AS-012 against the previous scan of this exact target.

    Signed over name, description and inferred permissions - deliberately
    not line numbers, which shift whenever unrelated code earlier in the
    file changes and would fire this on every commit rather than on an
    actual change to what a tool claims to do.
    """
    current = [
        PinnedSignature(
            f"{_TOOL_SIGNATURE_PREFIX}{tool.name}",
            hash_signature(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "permissions": sorted(p.value for p in tool.permissions),
                }
            ),
        )
        for tool in tools
    ]
    previous = [
        PinnedSignature(key, value)
        for key, value in config.previous_signatures.items()
        if key.startswith(_TOOL_SIGNATURE_PREFIX)
    ]
    config.computed_signatures.extend((p.server_name, p.signature_hash) for p in current)
    return diff_signatures(scan_id, previous, current)


def _partition_safe_remote_entries(
    mcp_entries: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Splits MCP entries into the ones safe to probe and the reasons the
    rest are not.

    Aevrin never executes a submitted stdio command, and never lets a
    submitted URL reach loopback, metadata, or private networks. Both
    refusals are reported rather than silently narrowing the scan.
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


def _probe_live_servers(
    scan: Scan,
    mcp_entries: dict[str, dict[str, Any]],
    config: PipelineConfig,
    emit: OnFindings,
) -> tuple[list[McpTool], list[str], list[str]]:
    """A `tools/list` handshake against every entry that passed validation."""
    if not mcp_entries:
        return [], [], []

    safe_entries, limitations = _partition_safe_remote_entries(mcp_entries)
    for entry in mcp_entries.values():
        if not isinstance(entry, dict):
            continue
        emit(
            check_weak_auth(
                scan.id,
                TransportInfo(
                    url=entry.get("url") if isinstance(entry.get("url"), str) else None,
                    has_auth_header=bool(entry.get("headers")),
                    has_api_key_env=any(
                        "key" in key.lower() or "token" in key.lower()
                        for key in (entry.get("env") or {})
                    ),
                ),
            )
        )
    if not safe_entries:
        return [], limitations, []

    errors: list[str] = []
    tools: list[McpTool] = []
    try:
        inspections = inspect_remote_servers(safe_entries)
    except Exception as exc:  # noqa: BLE001 - remote protocol errors are isolated
        return [], limitations, [f"live MCP handshake: {type(exc).__name__}: {exc}"]

    signatures = [PinnedSignature(i.server_name, i.signature_hash) for i in inspections]
    config.computed_signatures.extend((s.server_name, s.signature_hash) for s in signatures)
    previous = [
        PinnedSignature(name, value)
        for name, value in config.previous_signatures.items()
        if not name.startswith(_TOOL_SIGNATURE_PREFIX)
    ]
    emit(diff_signatures(scan.id, previous, signatures))
    for inspection in inspections:
        tools.extend(inspection.tools)
    return tools, limitations, errors


# --------------------------------------------------------------------------
# Behavior analysis


def _read_source_for_join(repo_dir: str, findings: list[Finding]) -> dict[str, str]:
    """Just the files a behavior finding actually landed in, read fresh from
    disk for `capability_map.attribute_findings_to_tools`."""
    paths = {f.location.file_path for f in findings if f.location.file_path}
    sources: dict[str, str] = {}
    for relative_path in paths:
        try:
            with open(
                os.path.join(repo_dir, relative_path), encoding="utf-8", errors="ignore"
            ) as handle:
                sources[relative_path] = handle.read()
        except OSError:
            continue
    return sources


def _run_behavior_stage(
    scan: Scan,
    repo_dir: str | None,
    tools: list[McpTool],
    stage: ScanStage,
    on_stage: OnStage,
    emit: OnFindings,
    errors: list[str],
) -> None:
    """Aevrin's own MCP-aware Semgrep taint pack, joined to the specific tool
    whose handler contains each sink.

    This is the only place in the product that produces *observed* evidence
    rather than declared evidence: a tool argument reaching a shell, a file
    write, or a credential read is dataflow, not a keyword. It is also why
    Semgrep the engine survives the removal of Semgrep the generic ruleset -
    the rules here are Aevrin's own, local, and MCP-specific.
    """
    if not repo_dir:
        _mark(
            stage,
            StageStatus.SKIPPED,
            on_stage,
            error="No source repository to analyze for this target type.",
        )
        return
    if not tools:
        _mark(
            stage,
            StageStatus.SKIPPED,
            on_stage,
            error=(
                "No declared MCP tools were found in source, so there is nothing for this "
                "stage to trace arguments from."
            ),
        )
        return

    _mark(stage, StageStatus.RUNNING, on_stage)
    findings, error = _run_isolated(
        "aevrin-mcp-behavior", lambda: McpBehaviorAdapter().run(scan.id, repo_dir)
    )
    if findings:
        _normalize_paths(findings, repo_dir)
        attribute_findings_to_tools(tools, findings, _read_source_for_join(repo_dir, findings))
        # Only meaningful once a finding is attributed to a specific tool:
        # comparing against the right tool's own declaration is the point.
        flag_undeclared_capabilities(tools, findings)
    emit(findings)
    if error:
        errors.append(error)
    _mark(stage, StageStatus.FAILED if error else StageStatus.DONE, on_stage, error=error)


# --------------------------------------------------------------------------
# Credential exposure and supply chain


def _run_secrets_stage(
    scan_id: UUID,
    repo_dir: str,
    stage: ScanStage,
    on_stage: OnStage,
    emit: OnFindings,
    errors: list[str],
) -> bool:
    """Returns True iff the scanner actually ran.

    One tool, not two. Gitleaks was removed as a duplicate: it matched the
    same patterns over the same tree without TruffleHog's live verification,
    and a verified credential - one confirmed to still work - is a
    materially different finding from a string that looks like one.
    """
    _mark(stage, StageStatus.RUNNING, on_stage)
    findings, error = _run_isolated(
        "trufflehog", lambda: TruffleHogAdapter().run(scan_id, repo_dir)
    )
    emit(_normalize_paths(findings, repo_dir))
    if error:
        errors.append(error)
    _mark(stage, StageStatus.FAILED if error else StageStatus.DONE, on_stage, error=error)
    return error is None


def _run_dependencies_stage(
    scan_id: UUID,
    repo_dir: str,
    stage: ScanStage,
    on_stage: OnStage,
    emit: OnFindings,
    errors: list[str],
) -> bool:
    """Returns True iff the scanner actually ran.

    Published advisories against the MCP server's own dependency tree
    (AS-004). Development-only advisories are dropped in postprocessing and
    the count is reported; see `pipeline/postprocess.py`.
    """
    _mark(stage, StageStatus.RUNNING, on_stage)
    findings, error = _run_isolated(
        "osv-scanner", lambda: OsvScannerAdapter().run(scan_id, repo_dir)
    )
    emit(_normalize_paths(findings, repo_dir))
    if error:
        errors.append(error)
    _mark(stage, StageStatus.FAILED if error else StageStatus.DONE, on_stage, error=error)
    return error is None


# --------------------------------------------------------------------------


def _discover_mcp_entries(
    target_type: TargetType, target: str, repo_dir: str | None
) -> dict[str, dict[str, Any]]:
    """Best-effort MCP server entrypoint discovery. A live-server target is
    trivial (the target IS the entrypoint); a repo target is searched for a
    committed client config, which most server repositories do not have."""
    if target_type == TargetType.LIVE_MCP_SERVER:
        return {"target-server": {"url": target}}
    if target_type == TargetType.CONFIG_PASTE:
        try:
            parsed = json.loads(target)
        except json.JSONDecodeError:
            return {}
        entries = parsed.get("mcpServers", parsed) if isinstance(parsed, dict) else {}
        return entries if isinstance(entries, dict) else {}
    if repo_dir:
        for candidate in (".mcp/config.json", "claude_desktop_config.json", "mcp.json", ".mcp.json"):
            path = os.path.join(repo_dir, candidate)
            if not os.path.exists(path):
                continue
            try:
                with open(path, encoding="utf-8") as handle:
                    parsed = json.load(handle)
            except (OSError, json.JSONDecodeError):
                continue
            entries = parsed.get("mcpServers", parsed) if isinstance(parsed, dict) else {}
            if isinstance(entries, dict):
                return entries
    return {}
