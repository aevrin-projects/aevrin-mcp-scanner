# aevrin

[![PyPI version](https://img.shields.io/pypi/v/aevrin.svg)](https://pypi.org/project/aevrin/)
[![Python versions](https://img.shields.io/pypi/pyversions/aevrin.svg)](https://pypi.org/project/aevrin/)
[![License](https://img.shields.io/pypi/l/aevrin.svg)](https://github.com/aevrin-projects/aevrin-mcp-scanner/blob/master/LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/aevrin.svg)](https://pypi.org/project/aevrin/)
[![Publish status](https://github.com/aevrin-projects/aevrin-mcp-scanner/actions/workflows/publish.yml/badge.svg)](https://github.com/aevrin-projects/aevrin-mcp-scanner/actions/workflows/publish.yml)

Aevrin MCP Security Scanner CLI. Wraps the same open-source scanner binaries and normalization logic (`aevrin-scanner-core`) that the Aevrin backend uses, run locally against your own machine — no network call required unless you pass `--upload`.

## Install

```bash
pip install aevrin
```

Requires Docker (each scanner runs in its own disposable container — see the main repo README for why).

## Usage

```bash
aevrin scan ./my-mcp-server
aevrin scan github.com/owner/repo
aevrin scan https://my-live-server.example.com --json
aevrin scan ./my-mcp-server --fail-on high
aevrin scan ./my-mcp-server --upload   # requires AEVRIN_API_KEY env var
```

Target type is auto-detected: a `github.com` URL scans the full pipeline (static analysis, secrets, dependencies, tool-description checks); any other `http(s)://` URL is treated as a live MCP server (manifest-level checks only); anything that exists on disk is scanned as a local path (full pipeline, no cloning).

### Flags

| Flag | Behavior |
|---|---|
| `--json` | Machine-readable JSON on stdout instead of a formatted table. |
| `--upload` | Pushes the result to your Aevrin account. Requires `AEVRIN_API_KEY`, set from your account's API keys settings page — never required for a local-only scan. |
| `--fail-on <severity>` | Minimum severity that causes a non-zero exit code. One of `critical`, `high`, `medium`, `low`, `info`. Defaults to `high` (both `critical` and `high` findings fail the build). |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Clean — no findings at or above the `--fail-on` threshold. |
| `1` | Findings at or above the `--fail-on` threshold were found. |
| `2` | Misuse — bad arguments, a target that couldn't be resolved, every scan stage failed to run, or `--upload` failed. |

Results go to stdout; stage progress and diagnostics go to stderr — safe to pipe `--json` output without stage-progress noise mixed in.

### Example output

```
[✓] static analysis
[✓] secrets
[✓] dependencies
[✓] tool description check
[✓] aggregating

Target: ./my-mcp-server
Score:  62/100  Significant risk — do not deploy as-is

┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ Severity ┃ Title                ┃ OWASP category                      ┃ Tool    ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━┩
│ CRITICAL │ Hardcoded secret     │ MCP01: Token Mismanagement          │ trivy   │
│ HIGH     │ subprocess shell true│ MCP05: Command Injection, ...       │ semgrep │
└──────────┴──────────────────────┴──────────────────────────────────────┴─────────┘
```

## Development

```bash
uv sync
uv run pytest tests -v
uv run ruff check .
uv run mypy src
```
