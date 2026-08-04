from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import httpx
import typer
from aevrin_scanner_core import Finding, ScanStage, ScanStatus, Severity
from aevrin_scanner_core.pipeline import PipelineConfig, run_pipeline

from . import output
from .auth import (
    HOOK_CREDENTIALS_PATH,
    DeviceLoginError,
    api_url,
    clear_credentials,
    device_login,
    load_api_key,
    save_credentials,
)
from .target_detection import TargetDetectionError, detect_target
from .upload import UploadError, upload_scan

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


@app.command()
def scan(
    target: Annotated[str, typer.Argument(help="GitHub URL, local path, or live MCP server URL.")],
    json_output: Annotated[bool, typer.Option("--json", help="Machine-readable JSON output.")] = False,
    upload: Annotated[
        bool,
        typer.Option(
            "--upload/--no-upload",
            help="Save results to your Aevrin dashboard. On by default when logged in — pass "
            "--no-upload for a purely local, ephemeral scan (e.g. in CI, where you don't want scan "
            "history persisted).",
        ),
    ] = True,
    fail_on: Annotated[
        str, typer.Option("--fail-on", help="Minimum severity that causes a non-zero exit code.")
    ] = "high",
) -> None:
    """Run the full Aevrin scan pipeline against TARGET."""
    # Usage is metered server-side now (a purely local counter can be edited
    # in an open-source CLI) — a scan without a logged-in account has
    # nothing to meter against, so it fails fast here rather than degrading
    # to a crippled local-only mode (explicit addendum §2 requirement).
    api_key = load_api_key()
    if not api_key:
        output.print_error(
            "Not logged in. Aevrin's free tier includes 5 CLI scans a month — "
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

    try:
        fail_on_severity = Severity(fail_on.lower())
    except ValueError:
        output.print_error(
            f"Invalid --fail-on value '{fail_on}'. Expected one of: "
            f"{', '.join(s.value for s in Severity)}."
        )
        raise typer.Exit(code=2) from None

    try:
        target_type, normalized_target = detect_target(target)
    except TargetDetectionError as exc:
        output.print_error(str(exc))
        raise typer.Exit(code=2) from None

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
        # otherwise-successful scan into a failure — that would be a bad
        # surprise in a CI pipeline that only cares about the scan result.
        try:
            upload_scan(result)
            if not json_output:
                output.stderr_console.print("[green]Saved to your Aevrin dashboard.[/green]")
        except UploadError as exc:
            output.print_error(f"Scan completed, but saving to your dashboard failed: {exc}")

    if result.status == ScanStatus.INCOMPLETE:
        # Non-zero unconditionally — independent of --fail-on — so a broken
        # environment (Docker down, missing binary, no network) can never
        # look like a clean pass in CI or a hook check. A distinct exit code
        # (3) lets callers tell "incomplete" apart from "quota/auth error"
        # (2) and "findings at/above --fail-on" (1).
        raise typer.Exit(code=3)

    worst = max(
        (f.severity for f in result.findings if not f.not_tested),
        key=lambda s: _SEVERITY_RANK[s],
        default=None,
    )
    if worst is not None and _SEVERITY_RANK[worst] >= _SEVERITY_RANK[fail_on_severity]:
        raise typer.Exit(code=1)
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
    # hook_script.py is stdlib-only on purpose (see its own docstring) — it
    # needs to start fast on nearly every Bash/Write tool call without
    # depending on the full Typer app bootstrapping. It ships inside this
    # package (installed via pip/pipx) specifically so `hook setup` can point
    # Claude Code straight at the installed copy — no separate repo checkout
    # needed for real users.
    from . import hook_script

    # shlex.quote — an unquoted path breaks the moment it contains a space
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
        "hooks — don't overwrite the file):\n"
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
    findings. Use after reviewing the risk — this doesn't fix or dismiss
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
    output.stderr_console.print(f"[green]Override granted[/green] — retry the install now. Expires {expires_at}.")


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
    """Update a finding's triage status — the "false report" action: mark a
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
def fix(
    finding_id: Annotated[str, typer.Argument(help="Finding ID, e.g. from a hook block message or --json scan output.")],
) -> None:
    """Generate an automatic fix for one finding: Claude Sonnet drafts a
    patch, the original scanner re-runs against it to confirm the finding
    actually clears, then a draft pull request is opened — never a merge,
    and never a PR that wasn't independently re-verified. Pro/Team only."""
    api_key = load_api_key() or load_api_key(HOOK_CREDENTIALS_PATH)
    if not api_key:
        output.print_error("Not logged in. Run `aevrin login` (or `aevrin hook setup`) first.")
        raise typer.Exit(code=2)
    output.stderr_console.print("[dim]Generating fix — this can take a minute…[/dim]")
    try:
        resp = httpx.post(
            f"{api_url()}/findings/{finding_id}/fix",
            headers={"X-API-Key": api_key},
            timeout=180,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        try:
            detail = exc.response.json().get("detail", detail)
        except ValueError:
            pass
        output.print_error(f"Could not run Fix It ({exc.response.status_code}): {detail}")
        raise typer.Exit(code=2) from None
    except httpx.HTTPError as exc:
        output.print_error(f"Could not reach {api_url()}: {exc}")
        raise typer.Exit(code=2) from None

    result = resp.json()
    if result["status"] == "fixed":
        output.stderr_console.print(f"[green]Fix It opened a draft pull request:[/green] {result['pr_url']}")
    elif result["status"] == "needs_github_connection":
        output.stderr_console.print(
            f"[yellow]GitHub isn't connected yet.[/yellow] Approve access, then retry: {result['install_url']}"
        )
        raise typer.Exit(code=2)
    else:
        output.print_error(result.get("failure_reason") or "Could not generate a fix for this finding.")
        raise typer.Exit(code=1)


@app.command()
def version() -> None:
    """Print the installed aevrin CLI version."""
    from importlib.metadata import version as pkg_version

    typer.echo(pkg_version("aevrin"))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
