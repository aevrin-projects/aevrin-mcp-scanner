"""The scan pipeline: resolve a target, run the server, grade what it exposes.

One engine, five stages, no branching security logic. Everything a scan
concludes comes from `mcp/tooltrust.py`; this file decides what to point it
at, records what happened, and turns the engine's verdict into a `Scan`.

The shape follows from a single decision: the security target is the running
MCP server, not the repository that happens to contain its source. A
repository is only ever a way of finding out which server to start. That is
why cloning is not a stage of its own any more - it is part of resolving -
and why a repository that publishes no runnable package ends the scan
honestly rather than falling back to scanning source files for something to
say.

The stages a reader sees map exactly onto what actually happens:

    resolving   - work out the command that starts this server
    launching   - start it, in a container that assumes it is hostile
    enumerating - complete the MCP handshake and read its tools
    analyzing   - run the rules over those tool definitions
    grading     - roll the per-tool verdicts up and write the summary

A scan that stops early stops at a named stage with a reason attached. It is
never completed-with-zero-findings, because that is indistinguishable from a
clean server.
"""

from __future__ import annotations

import re
import shutil
import subprocess  # nosec B404 - fixed argv, shell=False, sanitized env
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from ..classification.grouping import group_by_rule
from ..execution.runner import sanitized_subprocess_env
from ..mcp.resolve import (
    ResolvedTarget,
    UnresolvableTarget,
    from_explicit_command,
    from_repository,
)
from ..mcp.risk import grade_scan
from ..mcp.tooltrust import (
    SCANNER_NAME,
    SCANNER_VERSION,
    ScannerOutputError,
    ScanReport,
    ServerLaunchError,
    scan_live_server,
)
from ..models import (
    Finding,
    InvocationChannel,
    Scan,
    ScanStage,
    ScanStatus,
    StageName,
    StageStatus,
    TargetType,
)

OnStage = Callable[[ScanStage], None]
OnFindings = Callable[[list[Finding]], None]


@dataclass
class PipelineConfig:
    github_token: str | None = None
    clone_depth: int = 1
    # Which surface asked. Recorded on the scan; never changes the result.
    invocation_channel: InvocationChannel = InvocationChannel.DASHBOARD
    # A command the caller already knows, e.g. `aevrin scan mcp "npx -y x"`.
    # Takes precedence over anything derived from a repository: the user
    # telling us how to start their server is better evidence than a manifest.
    server_command: str | None = None
    env: dict[str, str] = field(default_factory=dict)


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


_CLONE_URL_TOKEN_RE = re.compile(r"://x-access-token:[^@\s]+@")


def _redact_token(text: str, token: str | None) -> str:
    if token:
        text = text.replace(token, "***")
    return _CLONE_URL_TOKEN_RE.sub("://x-access-token:***@", text)


def _clone(github_url: str, workdir: str, config: PipelineConfig) -> str:
    """Shallow-clone a repository, only to read its manifests.

    Depth 1: nothing here needs history. The repository is not scanned, it is
    consulted for the name of the package to launch.
    """
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
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        # str(exc) includes the full argv, which carries our token in
        # plaintext if one was used. This string is persisted and rendered
        # back to the user, so it is redacted before it goes anywhere.
        raise UnresolvableTarget(
            f"the repository could not be cloned: {_redact_token(str(exc), config.github_token)}"
        ) from exc
    return repo_dir


def _resolve(
    target_type: TargetType, target: str, workdir: str, config: PipelineConfig
) -> ResolvedTarget:
    if config.server_command:
        return from_explicit_command(config.server_command)
    if target_type == TargetType.LIVE_MCP_SERVER:
        return from_explicit_command(target)
    if target_type == TargetType.LOCAL_PATH:
        return from_repository(Path(target))
    if target_type == TargetType.GITHUB_REPO:
        return from_repository(Path(_clone(target, workdir, config)))
    raise UnresolvableTarget(
        f"Aevrin cannot start an MCP server from a {target_type.value} target."
    )


def _incomplete(
    scan: Scan,
    stage: ScanStage,
    on_stage: OnStage,
    reason: str,
    remaining: list[ScanStage],
) -> Scan:
    """End the scan at the stage that could not continue.

    The grade stays None and the status stays INCOMPLETE. This is the single
    most important path in the file: every way a scan can fail leads here,
    and none of them may produce a letter, a score, or an empty findings list
    that reads as a clean result.
    """
    _mark(stage, StageStatus.FAILED, on_stage, error=reason)
    for later in remaining:
        _mark(later, StageStatus.SKIPPED, on_stage, error="An earlier stage did not complete.")
    scan.unreliable_stages = [stage.name]
    scan.status = ScanStatus.INCOMPLETE
    scan.grade = None
    scan.risk_score = None
    scan.completed_at = datetime.now(timezone.utc)
    return scan


def run_pipeline(
    target_type: TargetType,
    target: str,
    config: PipelineConfig,
    on_stage: OnStage,
    on_findings: OnFindings,
    scan_id: UUID | None = None,
) -> Scan:
    scan_id = scan_id or uuid4()
    scan = Scan(
        id=scan_id,
        target_type=target_type,
        target=target,
        status=ScanStatus.RUNNING,
        scanner_name=SCANNER_NAME,
        scanner_version=SCANNER_VERSION,
        invocation_channel=config.invocation_channel,
    )
    scan.stages = [ScanStage(scan_id=scan_id, name=name) for name in StageName]
    stages = {s.name: s for s in scan.stages}
    order = list(StageName)

    def after(name: StageName) -> list[ScanStage]:
        return [stages[n] for n in order[order.index(name) + 1 :]]

    workdir = tempfile.mkdtemp(prefix="aevrin-scan-")
    try:
        # ---------------------------------------------------------- resolving
        _mark(stages[StageName.RESOLVING], StageStatus.RUNNING, on_stage)
        try:
            resolved = _resolve(target_type, target, workdir, config)
        except UnresolvableTarget as exc:
            scan.mcp_detected = False
            return _incomplete(
                scan,
                stages[StageName.RESOLVING],
                on_stage,
                str(exc),
                after(StageName.RESOLVING),
            )
        scan.server_command = resolved.command
        _mark(stages[StageName.RESOLVING], StageStatus.DONE, on_stage)

        # ------------------------------------------- launching + enumerating
        #
        # One engine call covers both: it starts the server, completes the
        # handshake and reads the tool list in a single run. They stay two
        # stages because they fail for different reasons and a reader needs
        # to know which happened - "the package does not exist" and "it
        # started but exposed no tools" call for different responses.
        _mark(stages[StageName.LAUNCHING], StageStatus.RUNNING, on_stage)
        try:
            report: ScanReport = scan_live_server(resolved.command, scan_id=scan_id)
        except ServerLaunchError as exc:
            scan.mcp_detected = None
            return _incomplete(
                scan,
                stages[StageName.LAUNCHING],
                on_stage,
                "The MCP server could not be launched or its tools could not be "
                f"enumerated, so this is not a complete security assessment. {exc}",
                after(StageName.LAUNCHING),
            )
        except ScannerOutputError as exc:
            return _incomplete(
                scan,
                stages[StageName.ANALYZING],
                on_stage,
                f"The scan result could not be read, so nothing here can be trusted. {exc}",
                after(StageName.ANALYZING),
            )
        _mark(stages[StageName.LAUNCHING], StageStatus.DONE, on_stage)

        _mark(stages[StageName.ENUMERATING], StageStatus.RUNNING, on_stage)
        scan.mcp_tools_declared = list(report.tools)
        scan.mcp_detected = bool(report.tools)
        if not report.tools:
            return _incomplete(
                scan,
                stages[StageName.ENUMERATING],
                on_stage,
                "The server started but exposed no tools, so there was nothing to "
                "assess. This is not the same as a server with nothing wrong with it.",
                after(StageName.ENUMERATING),
            )
        _mark(stages[StageName.ENUMERATING], StageStatus.DONE, on_stage)

        # ---------------------------------------------------------- analyzing
        _mark(stages[StageName.ANALYZING], StageStatus.RUNNING, on_stage)
        # Grouped before anything counts them. One rule firing identically on
        # twenty-four tools is one thing to fix, and rendering it as twenty-four
        # cards buries the finding that actually matters.
        findings = group_by_rule(report.findings)
        scan.findings = findings
        if findings:
            on_findings(findings)
        _mark(stages[StageName.ANALYZING], StageStatus.DONE, on_stage)

        # ------------------------------------------------------------ grading
        _mark(stages[StageName.GRADING], StageStatus.RUNNING, on_stage)
        result = grade_scan(
            findings,
            engine_risk_score=report.risk_score,
            engine_grade=report.grade,
            coverage_complete=True,
            tools_discovered=len(report.tools),
        )
        scan.risk_score = result.risk_score
        scan.grade = result.grade.value if result.grade else None
        scan.status = ScanStatus.INCOMPLETE if result.incomplete else ScanStatus.COMPLETED
        scan.completed_at = datetime.now(timezone.utc)
        _mark(stages[StageName.GRADING], StageStatus.DONE, on_stage)
        return scan
    finally:
        # Only ever the temporary workspace this function created; a
        # LOCAL_PATH scan must never have the caller's directory removed.
        shutil.rmtree(workdir, ignore_errors=True)
