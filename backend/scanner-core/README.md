# Aevrin Scanner Core

The shared scanning layer used by the Aevrin API and CLI. It resolves a target
to a launch command, runs the version-pinned MCP security engine against the
live server inside an isolated container, normalizes the engine's output into
one finding model, maps findings to the OWASP MCP Top 10, and records what
could not be assessed.

It does not decide security. The engine assigns severities, scores and grades;
this package presents them.

This package is primarily an internal runtime dependency. Most users should
install the [`aevrin`](https://pypi.org/project/aevrin/) CLI instead.

## Development

```bash
uv sync
uv run ruff check .
uv run mypy src
uv run pytest
```

Scans require a reachable Docker daemon. There is no subprocess fallback:
scanning an MCP server means starting it, which executes code published by
someone else, so a scan without a sandbox does not run at all. See
`DECISIONS.md` ADR-034.

## Security model

- The scan container receives an allow-listed environment - never the Supabase
  service-role key, a provider key, or a cloud credential. It runs non-root,
  read-only, with every capability dropped and a hard timeout.
- A launch command is read from the project's own manifest, never guessed from
  a repository name: guessing scans a different package and attributes the
  grade to the wrong publisher.
- A scan that could not launch or enumerate is INCOMPLETE and receives no
  grade; missing coverage is never presented as a clean scan.
- Prompt injection through live tool responses (MCP08) remains explicitly
  outside static-scan coverage.
