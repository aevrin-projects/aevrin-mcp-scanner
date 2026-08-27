# CLI reference

`aevrin`, published to PyPI (`pip install aevrin`) and npm
(`npm install -g aevrin`, which installs the Python package underneath).
Source: `backend/cli/aevrin_cli/main.py`. Verified against the registered
Typer commands directly, not restated from memory.

## `aevrin scan <target>`

Runs the full scan pipeline against `TARGET` (a GitHub URL, a local path,
or a live MCP server URL - detected automatically).

| Option | Default | Meaning |
|---|---|---|
| `--json` | off | Machine-readable JSON output instead of the terminal report. |
| `--upload` / `--no-upload` | `--upload` | Save the result to your Aevrin dashboard. Non-fatal on failure - a network hiccup doesn't turn a completed scan into a CLI failure. |
| `--fail-on <severity>` | `high` | Minimum severity (`info`/`low`/`medium`/`high`/`critical`) that causes a non-zero exit. |
| `--remote` | off | Upload a local folder's source and scan it on Aevrin's servers instead of locally - no Docker or scanner binaries needed on this machine. Only valid for a local path target. |

Requires login (`aevrin login`) - usage is metered server-side.

**Exit codes**: `0` clean; `1` a finding at or above `--fail-on`; `2` the
scan couldn't start (bad target, not logged in, quota exhausted, network
error) or an invalid argument; `3` the scan ran but its result can't be
trusted (`ScanStatus.INCOMPLETE` - a scanner category failed entirely).
`3` is returned **regardless of `--fail-on`**, specifically so a broken
scanning environment (Docker down, a binary missing) can never look like a
clean pass in CI.

## `aevrin agent scan`

Reports what AI coding agents installed on this machine (Claude Code,
Codex) have been configured to do. Reads configuration only - nothing is
executed, no agent is started.

| Option | Default | Meaning |
|---|---|---|
| `--project <path>` | `.` | Project directory whose agent configuration to include. |
| `--json` | off | Machine-readable output. |
| `--verbose` | off | List every configuration file actually read. |
| `--upload` | off | Send the posture snapshot to your dashboard. Off by default - this reads a machine's whole agent configuration, and sending it anywhere is opt-in. Carries no credential values even when uploaded, only credential metadata. |

Exits `0` whether or not any agent was found - this is a report, not a
pass/fail check.

## `aevrin login` / `aevrin logout`

Device-code login (opens a browser, no password entered in the terminal)
and credential removal, for the CLI's own stored API key.

## `aevrin hook setup` / `aevrin hook logout` / `aevrin hook allow <target>`

`hook setup` logs in **separately** from `aevrin login` (its own
credential store) and prints the exact `settings.json` snippet to merge
into a project's Claude Code configuration, wiring the `PreToolUse` hook
for `Bash` and `Write` tool calls. `hook logout` removes the hook's stored
credentials. `hook allow <target>` requests a short-lived override that
lets the hook allow the next install of `TARGET` through despite
unresolved high/critical findings - it does not fix or dismiss the
findings, it grants a one-time pass after you've reviewed the risk
yourself.

## `aevrin findings triage <finding-id> <status>`

Updates a finding's triage status. `<status>` is one of `open`, `fixed`,
`false_positive`. `--reason <text>` is **required** when marking
`false_positive` (stored with the triage audit record) and optional
otherwise. Accepts either the CLI's own login or the hook's.

## `aevrin version`

Prints the installed CLI version (also available as `aevrin --version`
at the top level, which exits immediately after printing).

## Environment

`GITHUB_TOKEN`, if set, is passed into the pipeline config for a local
scan (raises GitHub API rate limits for Scorecard/OSV lookups against
public repos it references) - unrelated to the API's own
`GITHUB_APP_*` variables that power "Connect GitHub" on the dashboard.
See [`ENVIRONMENT.md`](ENVIRONMENT.md).
