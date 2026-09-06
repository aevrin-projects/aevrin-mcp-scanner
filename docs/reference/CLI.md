# CLI reference

`aevrin`, published to PyPI (`pip install aevrin`) and npm
(`npm install -g aevrin`, which installs the Python package underneath).
Source: `backend/cli/aevrin_cli/main.py`. Verified against the registered
Typer commands directly, not restated from memory.

## `aevrin scan <target>`

Runs the full scan pipeline against `TARGET` (a GitHub URL, a local path,
or a live MCP server URL - detected automatically).

```
aevrin scan mcp "npx -y @playwright/mcp"
```

`scan mcp` takes the command that starts the server instead of a target to
resolve. It is the only form that needs no resolution at all, which matters
because resolving the wrong command grades somebody else's package under
this one's name: `microsoft/playwright-mcp` publishes as `@playwright/mcp`,
and an unrelated `playwright-mcp` also exists on npm. Every other target is
resolved from the project's own manifest, never from its repository name.

| Option | Default | Meaning |
|---|---|---|
| `--json` | off | Machine-readable JSON output instead of the terminal report. |
| `--upload` / `--no-upload` | `--upload` | Save the result to your Aevrin dashboard. Non-fatal on failure - a network hiccup doesn't turn a completed scan into a CLI failure. |
| `--fail-on <severity>` | `high` | Minimum severity (`info`/`low`/`medium`/`high`/`critical`) that causes a non-zero exit. |
| `--remote` | off | Upload a local folder's source and scan it on Aevrin's servers instead of locally - no Docker needed on this machine. Only valid for a local path target. |

Requires login (`aevrin login`) - usage is metered server-side.

**Exit codes**: `0` clean; `1` a finding at or above `--fail-on`; `2` the
scan couldn't start (bad target, not logged in, quota exhausted, network
error) or an invalid argument; `3` the scan ran but its result can't be
trusted (`ScanStatus.INCOMPLETE`). That covers a server that could not be
resolved, could not be launched, or returned no tools - all of which are
common and legitimate outcomes rather than errors.
`3` is returned **regardless of `--fail-on`**, specifically so a scan that
never assessed anything (Docker down, package unpublished, server needs
credentials to start) can never look like a clean pass in CI.

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

## `aevrin mcp-server`

Runs Aevrin as an MCP server over stdin/stdout, so an agent can scan a server
*before* it installs one. Add it to an agent's MCP configuration rather than
running it by hand.

```json
{ "mcpServers": { "aevrin": { "command": "aevrin", "args": ["mcp-server"] } } }
```

It exposes one tool, `scan_mcp_server(command)`, which runs the same pipeline
as `aevrin scan mcp` and returns the same verdict - grade, risk score, policy,
the tools it enumerated, and the findings. One scanner, one canonical result,
whichever surface asked.

The result is deliberately wordy about failure: an incomplete scan returns a
null grade *and* a `summary` that says in plain language that nothing was
established and the server must not be treated as safe. The consumer is a
language model, and a model reads prose more reliably than it reads a null.

Needs the optional extra, because the base CLI is what CI jobs and the Claude
Code hook install and neither speaks MCP:

```bash
pip install "aevrin[mcp]"
```

## `aevrin version`

Prints the installed CLI version (also available as `aevrin --version`
at the top level, which exits immediately after printing).

## Invocation channels

Every scan records which surface asked for it (`invocation_channel`), and it
never changes the result: the same server scanned from a laptop, a CI job or
an agent produces the same findings, the same grade and the same policy.

| Channel | How it is set |
|---|---|
| `cli` | the default for an interactive shell |
| `ci` | detected automatically from `CI`, `CONTINUOUS_INTEGRATION`, `BUILD_NUMBER` or `GITHUB_ACTIONS` |
| `mcp` | set by `aevrin mcp-server` |

There is deliberately no `--channel` flag. Every CI system already announces
itself, so a flag would only add a way to be wrong - a workflow that forgot it
would report `cli`, and nothing would break loudly enough for anyone to notice.

## Environment

`GITHUB_TOKEN`, if set, is passed into the pipeline config for a local
scan (raises GitHub API rate limits for OSV lookups against
public repos it references) - unrelated to the API's own
`GITHUB_APP_*` variables that power "Connect GitHub" on the dashboard.
See [`ENVIRONMENT.md`](ENVIRONMENT.md).
