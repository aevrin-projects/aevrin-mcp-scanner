# aevrin

[![PyPI version](https://img.shields.io/pypi/v/aevrin.svg)](https://pypi.org/project/aevrin/)
[![Python versions](https://img.shields.io/pypi/pyversions/aevrin.svg)](https://pypi.org/project/aevrin/)
[![License](https://img.shields.io/pypi/l/aevrin.svg)](https://github.com/aevrin-projects/aevrin-mcp-scanner/blob/master/LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/aevrin.svg)](https://pypi.org/project/aevrin/)
[![Publish status](https://github.com/aevrin-projects/aevrin-mcp-scanner/actions/workflows/publish.yml/badge.svg)](https://github.com/aevrin-projects/aevrin-mcp-scanner/actions/workflows/publish.yml)

Aevrin MCP Security Scanner CLI. Wraps the same open-source scanner binaries and normalization logic (`aevrin-scanner-core`) that the Aevrin backend uses, run locally against your own machine. Results save to your Aevrin dashboard automatically once you're logged in, pass `--no-upload` for a purely local, ephemeral scan.

## Install

```bash
python3 -m pip install --upgrade aevrin
```

The same CLI is also available through npm:

```bash
npm install --global aevrin
```

Requires Docker using Linux containers (each scanner runs in its own disposable container). On
Docker Desktop, assign at least 4 GB of memory and permit bind mounts from the system temporary
directory. Scanner images are version-pinned and pulled automatically when missing.

## Usage

```bash
aevrin scan ./my-mcp-server
aevrin scan github.com/owner/repo
aevrin scan https://my-live-server.example.com --json
aevrin scan ./my-mcp-server --fail-on high
aevrin scan ./my-mcp-server --no-upload   # skip saving to your dashboard (e.g. in CI)
```

Target type is auto-detected: a `github.com` URL scans the full pipeline (static analysis, secrets, dependencies, tool-description checks); another public `https://` URL is treated as a live MCP server (runtime description checks only); anything that exists on disk is scanned as a local path (full pipeline, no cloning). Private, loopback, metadata, credential-bearing, and plain-HTTP live targets are rejected. Aevrin never executes submitted stdio MCP commands.

### Flags

| Flag | Behavior |
|---|---|
| `--json` | Machine-readable JSON on stdout instead of a formatted table. |
| `--no-upload` | Skip saving the result to your Aevrin dashboard (on by default once logged in). Useful in CI, or for a purely local, ephemeral scan. |
| `--fail-on <severity>` | Minimum severity that causes a non-zero exit code. One of `critical`, `high`, `medium`, `low`, `info`. Defaults to `high` (both `critical` and `high` findings fail the build). |
| `--remote` | Scan a local folder on Aevrin's servers instead of this machine, so no Docker or scanner binary is needed locally. Local paths only. |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Clean: no findings at or above the `--fail-on` threshold. |
| `1` | Findings at or above the `--fail-on` threshold were found. |
| `2` | Couldn't start, authentication, quota, API, target, or flag error. |
| `3` | Incomplete: a required scanner category did not execute. This is never treated as a clean pass. |

Results go to stdout; stage progress and diagnostics go to stderr, safe to pipe `--json` output without stage-progress noise mixed in.

### Example output

```
[✓] static analysis
[✓] secrets
[✓] dependencies
[✓] tool description check
[✓] aggregating

Target: ./my-mcp-server
Score:  62/100  Significant risk; do not deploy as-is

┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ Severity ┃ Title                ┃ OWASP category                      ┃ Tool    ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━┩
│ CRITICAL │ Hardcoded secret     │ MCP01: Token Mismanagement          │ trivy   │
│ HIGH     │ subprocess shell true│ MCP05: Command Injection, ...       │ semgrep │
└──────────┴──────────────────────┴──────────────────────────────────────┴─────────┘
```

## Other commands

```bash
aevrin login / logout           # browser device-code login, credentials in ~/.aevrin
aevrin agent scan               # what the AI coding agents on this machine may do
aevrin agent scan --json        # versioned snapshot; never contains a credential value
aevrin hook setup               # log in the Claude Code hook, print its settings snippet
aevrin hook allow <target>      # short-lived override after a hook block
aevrin findings triage <id> <status> [--reason ...]
```

`agent scan` reads configuration only: no agent is started and nothing from a config file is
executed. Nothing leaves the machine without `--upload`. Full reference:
<https://mcp.aevrin.net/docs/cli>.

## Development

```bash
uv sync
uv run pytest tests -v
uv run ruff check .
uv run mypy aevrin_cli
```
