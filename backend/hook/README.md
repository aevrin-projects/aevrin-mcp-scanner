# aevrin-hook

A genuine Claude Code `PreToolUse` hook (a registered shell command, not an advisory MCP server) that blocks unsafe MCP server installs before they happen.

## What it intercepts

- `Bash` tool calls matching `claude mcp add ...`; extracts a URL if the server uses HTTP/SSE transport, or best-effort reconstructs a single-server config for stdio transport (`-- npx ...` / `-- docker run ...`).
- `Write` tool calls to `.mcp.json` or `claude_desktop_config.json`, parses the full written config for server URLs or stdio commands.

Everything else is ignored silently (exits 0, no output); this hook stays out of the way of unrelated tool calls.

`Edit` (partial-diff) writes to these files are intentionally **not** intercepted for content extraction: `Edit`'s `old_string`/`new_string` are a fragment, not the full resulting file, so there's nothing reliable to scan pre-edit. Full-file `Write` calls and `claude mcp add` commands are the two cases with enough information to act on.

## Decision logic

1. Check for a cached result first: one fast `POST /hook/cache` call (Supabase lookup, not a scan), with a 4-second timeout. Pasted configuration stays in the request body and is represented durably only by a hash label.
2. Clean cached scan → allow silently, with a small confirmatory note.
3. Cached scan has unresolved critical/high findings → **block**, with the score and specific findings (title, severity, OWASP category, file/line, remediation) in the denial reason, plus three options: fix it directly, `aevrin hook allow <target>` to install anyway, or `aevrin findings triage <id> false_positive --reason "..."` to dispute a finding with an auditable reason.
3a. An active `aevrin hook allow` override for this exact target → allow, once, without re-blocking.
3b. Cached scan's tools failed to run (Docker down, missing binary, no network) → **block as incomplete**, never allowed silently; see [Concepts → Incomplete scans](https://mcp.aevrin.net/docs/concepts#incomplete-scans).
4. No cached result → **allow**, with a visible "not yet scanned" warning. The actual scan runs server-side (`backend/api`'s `/hook/cache` endpoint fires it via `BackgroundTasks`); this script never runs or waits on a scan itself, only ever makes one short HTTP request.

Any failure (no API key configured, network error, timeout, malformed response) **fails open** (allows silently). A hook that blocks installs whenever Aevrin itself is unreachable is a hook that gets disabled by annoyed developers.

Full walkthrough: [mcp.aevrin.net/docs/hook](https://mcp.aevrin.net/docs/hook).

## Install

For real (pip/pipx-installed) users, `bin/aevrin_hook.py` is a symlink into `backend/cli/aevrin_cli/hook_script.py`; the same file ships inside the `aevrin` PyPI package, so `aevrin hook setup` logs in and prints a ready-to-paste `.claude/settings.json` snippet pointing at your own installed copy. No repo checkout needed:

```bash
aevrin hook setup
```

For developing this repo itself, `./backend/hook/install.sh` merges `settings.snippet.json` (which points at the symlinked path above) into `.claude/settings.json` instead (creates it if missing, merges via `jq` if it already exists).

## Why stdlib-only Python

`bin/aevrin_hook.py` has zero third-party dependencies on purpose; it's matched on nearly every `Bash`/`Write` tool call in a session, so it needs to start and exit fast and reliably without depending on a virtualenv being active or `pip install` having been run.

## Test

```bash
uv run --project ../scanner-core pytest tests/test_aevrin_hook.py -v
```

Tests cover target extraction (URL and stdio forms, both `Bash` and `Write` paths, unrelated calls correctly ignored) and the three decision-emitting functions. See the main repo's build log for a full live simulation (mock backend, real subprocess, block + allow-clean + allow-unscanned + fail-open-on-network-error, all verified).
