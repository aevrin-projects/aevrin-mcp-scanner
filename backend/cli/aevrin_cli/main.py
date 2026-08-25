from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import httpx
import typer
from aevrin_scanner_core import Finding, Scan, ScanStage, ScanStatus, Severity, TargetType
from aevrin_scanner_core.agents import discover_claude_code, managed_settings_path
from aevrin_scanner_core.pipeline import PipelineConfig, run_pipeline

from .rendering import output
from .rendering.agent_report import print_agent_report, print_no_agents
from .services.auth import (
    HOOK_CREDENTIALS_PATH,
    DeviceLoginError,
    api_url,
    clear_credentials,
    device_login,
    load_api_key,
    save_credentials,
)
from .services.remote_scan import RemoteScanError, run_remote_scan
from .services.source_archive import ArchiveTooLarge
from .services.target_detection import TargetDetectionError, detect_target
from .services.upload import UploadError, upload_agent_snapshot, upload_scan

app = typer.Typer(
    name="aevrin",
    help="Scan MCP servers for vulnerabilities using established open-source security tools.",
    no_args_is_help=True,
)

_SEVERITY_RANK: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


def _version_callback(show_version: bool) -> None:
    if show_version:
        from importlib.metadata import version as pkg_version

        typer.echo(pkg_version("aevrin"))
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show the installed version and exit."),
    ] = False,
) -> None:
    pass


def _authenticated_preflight() -> str:
    """Returns a usable API key, or exits with a message.

    Usage is metered server-side (a purely local counter can be edited in an
    open-source CLI), so a scan without a logged-in account has nothing to meter
    against. It fails fast here rather than degrading to a crippled local-only
    mode (explicit addendum §2 requirement).
    """
    api_key = load_api_key()
    if not api_key:
        output.print_error(
            "Not logged in. Aevrin's free tier includes 5 CLI scans a month, "
            "run `aevrin login` to get started."
        )
        raise typer.Exit(code=2)

    try:
        precheck = httpx.get(f"{api_url()}/cli/precheck", headers={"X-API-Key": api_key}, timeout=15)
    except httpx.HTTPError as exc:
        output.print_error(f"Could not reach {api_url()}: {exc}")
        raise typer.Exit(code=2) from None

    if precheck.status_code == 402:
        body = precheck.json()
        output.print_error(
            f"Your {body['bucket']} scan quota is used up for this billing period. "
            f"Resets {body['resets_at']}. Upgrade at {body['upgrade_url']}"
        )
        raise typer.Exit(code=2)
    if precheck.status_code == 401:
        output.print_error("Your login has expired or was revoked. Run `aevrin login` again.")
        raise typer.Exit(code=2)
    return api_key


def _parse_fail_on(fail_on: str) -> Severity:
    try:
        return Severity(fail_on.lower())
    except ValueError:
        output.print_error(
            f"Invalid --fail-on value '{fail_on}'. Expected one of: "
            f"{', '.join(s.value for s in Severity)}."
        )
        raise typer.Exit(code=2) from None


def _exit_code(result: Scan, fail_on_severity: Severity) -> int:
    """3 = the scan could not be trusted, 1 = real findings at or above the
    threshold, 0 = clean. Callers (CI, the hook) rely on telling these apart.
    """
    if result.status == ScanStatus.INCOMPLETE:
        # Non-zero unconditionally (independent of --fail-on), so a broken
        # environment (Docker down, missing binary, no network) can never look
        # like a clean pass in CI or a hook check.
        return 3
    worst = max(
        (f.severity for f in result.findings if not f.not_tested),
        key=lambda s: _SEVERITY_RANK[s],
        default=None,
    )
    if worst is not None and _SEVERITY_RANK[worst] >= _SEVERITY_RANK[fail_on_severity]:
        return 1
    return 0


@app.command()
def scan(
    target: Annotated[str, typer.Argument(help="GitHub URL, local path, or live MCP server URL.")],
    json_output: Annotated[bool, typer.Option("--json", help="Machine-readable JSON output.")] = False,
    upload: Annotated[
        bool,
        typer.Option(
            "--upload/--no-upload",
            help="Save results to your Aevrin dashboard. On by default when logged in, pass "
            "--no-upload for a purely local, ephemeral scan (e.g. in CI, where you don't want scan "
            "history persisted).",
        ),
    ] = True,
    fail_on: Annotated[
        str, typer.Option("--fail-on", help="Minimum severity that causes a non-zero exit code.")
    ] = "high",
    remote: Annotated[
        bool,
        typer.Option(
            "--remote",
            help="Scan a local folder on Aevrin's servers instead of on this machine. Uploads the "
            "folder's source, so every scanner runs without Docker or any scanner binary installed "
            "here. Excludes .git, dependencies, and build output.",
        ),
    ] = False,
) -> None:
    """Run the full Aevrin scan pipeline against TARGET."""
    _authenticated_preflight()
    fail_on_severity = _parse_fail_on(fail_on)

    try:
        target_type, normalized_target = detect_target(target)
    except TargetDetectionError as exc:
        output.print_error(str(exc))
        raise typer.Exit(code=2) from None

    if remote:
        if target_type is not TargetType.LOCAL_PATH:
            output.print_error(
                "--remote is for local folders. A GitHub URL or live server is already reachable "
                "from Aevrin's servers; start that scan from the dashboard."
            )
            raise typer.Exit(code=2)
        _run_remote_scan(normalized_target, json_output, fail_on_severity)
        return

    config = PipelineConfig(github_token=os.environ.get("GITHUB_TOKEN"))

    def on_stage(stage: ScanStage) -> None:
        if not json_output:
            output.print_stage_update(stage.name.value, stage.status.value, stage.error)

    def on_findings(findings: list[Finding]) -> None:
        pass  # collected on the returned Scan object; nothing to stream for the CLI

    result = run_pipeline(
        target_type=target_type,
        target=normalized_target,
        config=config,
        on_stage=on_stage,
        on_findings=on_findings,
        scan_id=uuid4(),
    )

    if json_output:
        output.print_json_report(result)
    else:
        output.print_terminal_report(result)

    if upload:
        # Non-fatal: upload is on by default now (not an explicit ask), so a
        # transient network hiccup syncing to the dashboard shouldn't turn an
        # otherwise-successful scan into a failure, that would be a bad
        # surprise in a CI pipeline that only cares about the scan result.
        try:
            upload_scan(result)
            if not json_output:
                output.stderr_console.print("[green]Saved to your Aevrin dashboard.[/green]")
        except UploadError as exc:
            output.print_error(f"Scan completed, but saving to your dashboard failed: {exc}")

    raise typer.Exit(code=_exit_code(result, fail_on_severity))


def _run_remote_scan(folder: str, json_output: bool, fail_on_severity: Severity) -> None:
    """Uploads the folder, waits for the server, renders the same report.

    Already saved to the dashboard by definition -- the server ran it -- so
    there is no upload step afterwards the way a local scan has.
    """
    def progress(message: str) -> None:
        if not json_output:
            output.stderr_console.print(rf"[dim]\[…][/dim] {message}")

    if not json_output:
        output.stderr_console.print(
            "[dim]--remote uploads this folder's source to Aevrin so the server can scan it. "
            "Version control history, dependencies, and build output are excluded.[/dim]"
        )

    try:
        result = run_remote_scan(folder, progress)
    except (RemoteScanError, ArchiveTooLarge) as exc:
        output.print_error(str(exc))
        raise typer.Exit(code=2) from None

    if json_output:
        output.print_json_report(result)
    else:
        output.print_terminal_report(result)
        output.stderr_console.print("[green]Scanned on Aevrin's servers; saved to your dashboard.[/green]")

    raise typer.Exit(code=_exit_code(result, fail_on_severity))


agent_app = typer.Typer(help="Inspect the AI coding agents installed on this machine.")
app.add_typer(agent_app, name="agent")


@agent_app.command("scan")
def agent_scan(
    project: Annotated[
        str, typer.Option("--project", help="Project directory whose agent configuration to include.")
    ] = ".",
    json_output: Annotated[bool, typer.Option("--json", help="Machine-readable JSON output.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", help="List every configuration file read.")] = False,
    upload: Annotated[
        bool, typer.Option("--upload", help="Send the snapshot to your Aevrin dashboard.")
    ] = False,
) -> None:
    """Report what the AI coding agents here have been allowed to do.

    Reads configuration only. Nothing is executed and no agent is started.
    Nothing leaves this machine unless you pass --upload, and even then the
    snapshot carries no credential values.
    """
    project_root = os.path.abspath(project)
    agent = discover_claude_code(project_root=project_root)

    if agent is None:
        if json_output:
            print(json.dumps({"agents": []}, indent=2))
        else:
            print_no_agents([
                os.path.join(os.path.expanduser("~"), ".claude", "settings.json"),
                os.path.join(os.path.expanduser("~"), ".claude.json"),
                os.path.join(project_root, ".claude", "settings.json"),
                os.path.join(project_root, ".mcp.json"),
                managed_settings_path(),
            ])
        raise typer.Exit(code=0)

    if json_output:
        print(json.dumps({"agents": [agent.model_dump(mode="json")]}, indent=2))
    else:
        print_agent_report(agent, verbose=verbose)

    if upload:
        try:
            upload_agent_snapshot([agent])
        except UploadError as exc:
            output.print_error(str(exc))
            raise typer.Exit(code=2) from None
        output.stderr_console.print("[green]Snapshot sent to your dashboard.[/green]")

    raise typer.Exit(code=0)


@app.command()
def login() -> None:
    """Log in to your Aevrin account (opens a browser, no password needed here)."""
    if load_api_key():
        output.stderr_console.print("[yellow]Already logged in. Run `aevrin logout` first to switch accounts.[/yellow]")
        raise typer.Exit(code=0)

    def on_prompt(user_code: str, verification_uri: str) -> None:
        output.stderr_console.print(f"First, copy your one-time code: [bold]{user_code}[/bold]")
        output.stderr_console.print(f"Then visit: [bold]{verification_uri}[/bold]")
        output.stderr_console.print("Opening your browser... waiting for approval.")

    try:
        api_key = device_login(client_kind="cli", on_prompt=on_prompt)
    except DeviceLoginError as exc:
        output.print_error(str(exc))
        raise typer.Exit(code=2) from None

    save_credentials(api_key)
    output.stderr_console.print("[green]Logged in.[/green]")


@app.command()
def logout() -> None:
    """Log out and remove the stored credentials."""
    clear_credentials()
    output.stderr_console.print("Logged out.")


hook_app = typer.Typer(help="Manage the Claude Code security hook.", no_args_is_help=True)
app.add_typer(hook_app, name="hook")


@hook_app.command("setup")
def hook_setup() -> None:
    """Log in for the Claude Code hook (separate from `aevrin login`) and
    print the settings.json snippet to install."""
    if load_api_key(HOOK_CREDENTIALS_PATH):
        output.stderr_console.print(
            "[yellow]Hook already logged in.[/yellow] Run `aevrin hook logout` first to switch "
            "accounts. Re-printing the settings.json snippet:"
        )
        print_hook_settings_snippet()
        raise typer.Exit(code=0)

    def on_prompt(user_code: str, verification_uri: str) -> None:
        output.stderr_console.print(f"First, copy your one-time code: [bold]{user_code}[/bold]")
        output.stderr_console.print(f"Then visit: [bold]{verification_uri}[/bold]")
        output.stderr_console.print("Opening your browser... waiting for approval.")

    try:
        api_key = device_login(client_kind="hook", on_prompt=on_prompt)
    except DeviceLoginError as exc:
        output.print_error(str(exc))
        raise typer.Exit(code=2) from None

    save_credentials(api_key, HOOK_CREDENTIALS_PATH)
    output.stderr_console.print("[green]Hook logged in.[/green]")
    print_hook_settings_snippet()


def print_hook_settings_snippet() -> None:
    # hook_script.py is stdlib-only on purpose (see its own docstring); it
    # needs to start fast on nearly every Bash/Write tool call without
    # depending on the full Typer app bootstrapping. It ships inside this
    # package (installed via pip/pipx) specifically so `hook setup` can point
    # Claude Code straight at the installed copy, no separate repo checkout
    # needed for real users.
    from . import hook_script

    # shlex.quote, an unquoted path breaks the moment it contains a space
    # (e.g. some pipx/npm install prefixes), since Claude Code runs this
    # `command` string through a shell: the path silently splits into
    # multiple bogus arguments and the hook exits before it ever reads
    # stdin, indistinguishable from the hook just not firing at all.
    script_command = f"python3 {shlex.quote(str(Path(hook_script.__file__).resolve()))}"
    snippet = json.dumps(
        {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": script_command, "timeout": 8}],
                    },
                    {
                        "matcher": "Write",
                        "hooks": [{"type": "command", "command": script_command, "timeout": 8}],
                    },
                ]
            }
        },
        indent=2,
    )
    output.stderr_console.print(
        "\nAdd this to your project's .claude/settings.json (merge with any existing "
        "hooks; don't overwrite the file):\n"
    )
    print(snippet)


@hook_app.command("logout")
def hook_logout() -> None:
    """Log out the hook and remove its stored credentials."""
    clear_credentials(HOOK_CREDENTIALS_PATH)
    output.stderr_console.print("Hook logged out.")


@hook_app.command("allow")
def hook_allow(
    target: Annotated[str, typer.Argument(help="The exact target the hook blocked (URL or repo it printed).")],
) -> None:
    """Install anyway: grants a short-lived override so the hook lets the
    next install of TARGET through despite unresolved high/critical
    findings. Use after reviewing the risk; this doesn't fix or dismiss
    the findings, it just doesn't block on them once."""
    api_key = load_api_key(HOOK_CREDENTIALS_PATH)
    if not api_key:
        output.print_error("Hook not logged in. Run `aevrin hook setup` first.")
        raise typer.Exit(code=2)
    try:
        resp = httpx.post(
            f"{api_url()}/hook/override", json={"target": target}, headers={"X-API-Key": api_key}, timeout=15
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        output.print_error(f"Could not reach {api_url()}: {exc}")
        raise typer.Exit(code=2) from None
    expires_at = resp.json()["expires_at"]
    output.stderr_console.print(f"[green]Override granted[/green]: retry the install now. Expires {expires_at}.")


findings_app = typer.Typer(help="Manage scan findings.", no_args_is_help=True)
app.add_typer(findings_app, name="findings")


@findings_app.command("triage")
def findings_triage(
    finding_id: Annotated[str, typer.Argument(help="Finding ID, e.g. from a hook block message or --json scan output.")],
    triage_status: Annotated[
        str, typer.Argument(help="New status: open, fixed, or false_positive.")
    ],
    reason: Annotated[
        str | None,
        typer.Option(
            "--reason",
            help="Required for false_positive reports; stored with the triage audit record.",
        ),
    ] = None,
) -> None:
    """Update a finding's triage status, the "false report" action: mark a
    finding you've reviewed and believe is wrong as false_positive so it
    stops blocking installs and is excluded from future risk summaries."""
    if triage_status == "false_positive" and not (reason and reason.strip()):
        output.print_error("False-positive reports require --reason with your review evidence.")
        raise typer.Exit(code=2)

    api_key = load_api_key() or load_api_key(HOOK_CREDENTIALS_PATH)
    if not api_key:
        output.print_error("Not logged in. Run `aevrin login` (or `aevrin hook setup`) first.")
        raise typer.Exit(code=2)
    try:
        resp = httpx.patch(
            f"{api_url()}/findings/{finding_id}",
            json={"triage_status": triage_status, "reason": reason},
            headers={"X-API-Key": api_key},
            timeout=15,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        output.print_error(f"Could not update finding ({exc.response.status_code}): {exc.response.text}")
        raise typer.Exit(code=2) from None
    except httpx.HTTPError as exc:
        output.print_error(f"Could not reach {api_url()}: {exc}")
        raise typer.Exit(code=2) from None
    output.stderr_console.print(f"[green]Finding {finding_id} marked {triage_status}.[/green]")


@app.command()
def version() -> None:
    """Print the installed aevrin CLI version."""
    from importlib.metadata import version as pkg_version

    typer.echo(pkg_version("aevrin"))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
