# Architecture overview

## Topology

```
                     +-----------------------------+
                     | Cloudflare Workers (2, OpenNext)|
                     | aevrin-web:  mcp.aevrin.net      |
                     | aevrin-docs: docs.mcp.aevrin.net |
                     +---------------+---------------+
                                     | HTTPS
                                     v
                     +-----------------------------+
                     |  AWS EC2 (Docker, behind Caddy)|
                     |  api.mcp.aevrin.net             |
                     |  backend/api (FastAPI)          |
                     +---+--------+--------+---------+
                         |        |        |
             PostgREST   |        |        | HTTPS (Fernet-decrypted
             (service    |        |        |  key, per call)
             role key)   |        |        v
                         |        |   Groq / OpenAI / Anthropic / Gemini
                         v        v
                  +-----------+  +------------------+
                  | Supabase  |  | Upstash Redis,    |
                  | Postgres  |  | Cloudflare R2,     |
                  | + Auth    |  | GitHub REST/App,   |
                  +-----------+  | Razorpay, DefectDojo|
                                 | official MCP Registry|
                                 +------------------+

        Independent of the above, reaching the API directly:
        - aevrin CLI (PyPI + npm wrapper)
        - Claude Code PreToolUse hook (bin/aevrin_hook.py, stdlib-only)
        - CI (`aevrin scan` in a pipeline)
```

The API is a single container with no privileged access requirement and no
hard dependency on one cloud vendor - nothing in the image names AWS.
Fargate/ECS is the current target; Azure Container Apps is the documented
fallback. See [`DEPLOYMENT.md`](DEPLOYMENT.md).

## The one engine, three surfaces

`backend/scanner-core` (`aevrin_scanner_core` on PyPI) is imported by both
`backend/api` and `backend/cli`. It owns:

- The `Scan` / `Finding` / `ScanStage` Pydantic models (single source of
  truth for what a finding *is*, everywhere).
- The scanner adapters and the pipeline orchestrator.
- OWASP MCP Top 10 classification, scoring, and `grade_mcp_server()`.
- MCP-server detection and agent-posture scoring.

Nothing above `scanner-core` re-implements any of this. A finding rendered
in the dashboard, a finding printed by the CLI, and a finding named in a
hook block message all came from the exact same `Finding` object.

## Layer boundaries, enforced not just documented

- **Backend** (`backend/api`): dependency direction is
  `routes → controllers → services → db/integrations/config/core`. Nothing
  imports upward. See [`BACKEND.md`](BACKEND.md).
- **Frontend** (`frontend/src`): Feature-Sliced Design,
  `app → views → widgets → features → entities → shared`, imports run
  downward only, enforced by `eslint.config.mjs`'s `no-restricted-imports`
  rule (a lint error, not a review comment). See [`FRONTEND.md`](FRONTEND.md).
- **Database**: Supabase's service-role key (used by `backend/api`)
  bypasses RLS by design, which makes the application layer - not
  Postgres - the actual tenancy boundary for most tables. RLS still
  matters for public marketplace reads and a handful of directly-exposed
  tables. See [`DATABASE.md`](DATABASE.md) and
  [`../security/SECURITY.md`](../security/SECURITY.md).

## Components at a glance

| Concern | Owned by |
|---|---|
| Scanning engine | `backend/scanner-core` |
| Scan orchestration, quota, triage | `backend/api/aevrin_api/services/{scan,quota,triage}.py` |
| Marketplace ingestion, ranking, grading | `backend/api/aevrin_api/services/marketplace/` |
| AI explanations, provider credentials, model catalogue | `backend/api/aevrin_api/services/ai/` |
| Billing | `backend/api/aevrin_api/services/reports/` (report generation), `controllers/billing_controller.py`, `integrations/razorpay_client.py` |
| Agent (Claude Code / Codex) discovery and posture | `backend/scanner-core/aevrin_scanner_core/agents/` |
| Auth (Supabase JWT verification, API keys) | `backend/api/aevrin_api/core/security.py` |
| Permissions/roles | `backend/api/aevrin_api/services/permissions.py` |
| Dashboard + public site | `frontend/src` (App Router) |
| Docs site (separate app/Worker) | `frontend-docs/src` (App Router) + `frontend-docs/content/` (MDX) |

See [`DATA_FLOWS.md`](DATA_FLOWS.md) for how these actually connect,
end to end, per major feature.
