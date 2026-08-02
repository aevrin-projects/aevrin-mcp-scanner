from __future__ import annotations

import os
from typing import Annotated
from uuid import uuid4

import typer
from aevrin_scanner_core import Finding, ScanStage, Severity, StageStatus
from aevrin_scanner_core.pipeline import PipelineConfig, run_pipeline

from . import output
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


@app.command()
def scan(
    target: Annotated[str, typer.Argument(help="GitHub URL, local path, or live MCP server URL.")],
    json_output: Annotated[bool, typer.Option("--json", help="Machine-readable JSON output.")] = False,
    upload: Annotated[
        bool, typer.Option("--upload", help="Upload results to your Aevrin account (requires AEVRIN_API_KEY).")
    ] = False,
    fail_on: Annotated[
        str, typer.Option("--fail-on", help="Minimum severity that causes a non-zero exit code.")
    ] = "high",
) -> None:
    """Run the full Aevrin scan pipeline against TARGET."""
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
        try:
            upload_scan(result)
            if not json_output:
                output.stderr_console.print("[green]Uploaded to your Aevrin account.[/green]")
        except UploadError as exc:
            output.print_error(str(exc))
            raise typer.Exit(code=2) from None

    all_stages_failed = result.stages and all(s.status == StageStatus.FAILED for s in result.stages)
    if all_stages_failed:
        raise typer.Exit(code=2)

    worst = max(
        (f.severity for f in result.findings if not f.not_tested),
        key=lambda s: _SEVERITY_RANK[s],
        default=None,
    )
    if worst is not None and _SEVERITY_RANK[worst] >= _SEVERITY_RANK[fail_on_severity]:
        raise typer.Exit(code=1)
    raise typer.Exit(code=0)


@app.command()
def version() -> None:
    """Print the installed aevrin CLI version."""
    from importlib.metadata import version as pkg_version

    typer.echo(pkg_version("aevrin"))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
