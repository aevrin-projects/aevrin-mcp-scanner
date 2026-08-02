# aevrin-api

FastAPI backend: orchestrates the scan pipeline (`packages/scanner-core`), persists to Supabase, talks to DefectDojo, serves the website and CLI upload.

## Run locally

```bash
cp .env.example .env   # fill in real values — see "Required secrets" below
uv sync
uv run uvicorn aevrin_api.main:app --reload --port 8000
```

## Test / lint / typecheck

```bash
uv run pytest tests -v
uv run ruff check .
uv run mypy src
```

## Required secrets not derivable from anywhere in this repo

- `SUPABASE_SERVICE_ROLE_KEY` — Supabase dashboard → Project Settings → API. Never exposed via MCP tools by design; must be pasted in manually. (No JWT secret needed — auth verification uses the project's JWKS endpoint, which handles key rotation automatically.)
- `API_KEY_PEPPER` — generate with `openssl rand -hex 32`.
- `DEFECTDOJO_URL` / `DEFECTDOJO_API_KEY` — populated once DefectDojo is deployed (Section 5 of the master build prompt); the API runs fine without them, DefectDojo push is best-effort and non-blocking.

Upstash Redis, Cloudflare R2, and `GITHUB_TOKEN` values are already available (see repo root `env.txt`, gitignored).
