# Aevrin Scanner Core

The shared scanning engine used by the Aevrin API and CLI. It runs the same
version-pinned scanner adapters, normalizes their output into one finding
model, maps findings to the OWASP MCP Top 10, records per-stage coverage, and
computes the report score.

This package is primarily an internal runtime dependency. Most users should
install the [`aevrin`](https://pypi.org/project/aevrin/) CLI instead.

## Development

```bash
uv sync
uv run ruff check .
uv run mypy src
uv run pytest
```

Scanner execution defaults to isolated Docker containers. The production API
uses `AEVRIN_EXECUTOR=subprocess` with the same pinned binaries baked into its
non-root container, because managed runtimes such as AWS Fargate do not
provide Docker-in-Docker.

## Security model

- Scanner subprocesses receive an allowlisted environment, not application or
  database credentials.
- Remote MCP inspection accepts only public HTTPS endpoints and never executes
  submitted stdio commands.
- A stage is marked incomplete when required tools fail; missing coverage is
  never presented as a clean scan.
- Prompt injection through live tool responses (MCP08) remains explicitly
  outside static-scan coverage.
