# Aevrin engineering documentation

This is the documentation for building Aevrin, not for using it. If you're
looking for user-facing product docs (how to install a marketplace listing,
how the CLI works as an end user, what a security grade means), that's the
public docs site: a separate app, `frontend-docs/`, sourced from
[`frontend-docs/content/`](../frontend-docs/content/) and published at
`docs.mcp.aevrin.net` - see `docs/OVERVIEW.md` for how the two relate.

Start at [`../CLAUDE.md`](../CLAUDE.md) if you haven't. It has the reading
order and the rules; this page is the map it points to.

## Getting started

- [`OVERVIEW.md`](OVERVIEW.md) - what Aevrin is, its components, and how
  data flows between them.

## Architecture

- [`architecture/OVERVIEW.md`](architecture/OVERVIEW.md) - system topology.
- [`architecture/BACKEND.md`](architecture/BACKEND.md) - API layering,
  scanner-core, CLI, npm wrapper, Claude Code hook.
- [`architecture/FRONTEND.md`](architecture/FRONTEND.md) - Feature-Sliced
  Design layers, routing, entity inventory.
- [`architecture/DATABASE.md`](architecture/DATABASE.md) - Supabase schema,
  RLS model, migration history.
- [`architecture/DEPLOYMENT.md`](architecture/DEPLOYMENT.md) - AWS/Docker
  backend, Cloudflare Workers frontend, CI/CD, publishing pipelines.
- [`architecture/DATA_FLOWS.md`](architecture/DATA_FLOWS.md) -
  authentication, scanning, marketplace ingestion, agent posture, AI
  review, and billing, each end to end.

## Security

- [`security/SECURITY.md`](security/SECURITY.md) - authentication,
  authorization, tenancy isolation, secret handling, SSRF protection,
  credential metadata, the local key files at the repository root.

## Engineering

- [`engineering/STANDARDS.md`](engineering/STANDARDS.md) - layering rules,
  naming, error handling, dependency policy, the simplicity rule.

## Testing

- [`testing/TESTING.md`](testing/TESTING.md) - test suites and commands
  for every package, what CI actually gates on, and the security test
  philosophy.

## MCP and AI-agent tooling

- [`mcp/MCP_USAGE.md`](mcp/MCP_USAGE.md) - which MCP tool to use for which
  kind of question, adapted to what's actually available on this project.

## Product features

- [`features/MCP_SCANNING.md`](features/MCP_SCANNING.md) - the scan
  pipeline, OWASP MCP Top 10, scanner adapters, trust grading.
- [`features/AGENT_POSTURE.md`](features/AGENT_POSTURE.md) - AI-agent
  discovery, capability/permission scoring, attack paths.
- [`features/MCP_MARKETPLACE.md`](features/MCP_MARKETPLACE.md) - registry
  ingestion, ranking, submissions, admin moderation.
- [`features/AI_REVIEW.md`](features/AI_REVIEW.md) - AI explanations:
  what the model receives, what it's structurally prevented from doing.
- [`features/BILLING.md`](features/BILLING.md) - plans, quotas, Razorpay
  integration.

## Reference

- [`reference/CLI.md`](reference/CLI.md) - every `aevrin` command.
- [`reference/API.md`](reference/API.md) - route inventory by domain.
- [`reference/ENVIRONMENT.md`](reference/ENVIRONMENT.md) - every
  environment variable, what it's for, whether it's secret.

## Process

- [`workflows/WORKFLOW.md`](workflows/WORKFLOW.md) - feature development,
  bug fixes, and the release sequence (product, CLI, npm, docs site).
- [`git/WORKFLOW.md`](git/WORKFLOW.md) - commit format, branch strategy,
  what never gets committed.
- [`writing/STANDARDS.md`](writing/STANDARDS.md) - UI copy, error message,
  and terminology conventions.

## Decisions and history

- [`../DECISIONS.md`](../DECISIONS.md) - architectural decision log,
  append-only.
- [`../ROADMAP.md`](../ROADMAP.md) - what's planned, in progress, or
  known debt.
- [`../CHANGELOG.md`](../CHANGELOG.md) - what shipped, and when.

Third-party provenance (what was consulted, what licence, what was
actually taken) lives with the feature it applies to rather than in a
separate file: `docs/features/MCP_MARKETPLACE.md` (registry and
marketplace-reference sources), `docs/features/AI_REVIEW.md` (provider
APIs, the LiteLLM evaluation), `docs/engineering/STANDARDS.md`
(dependency policy). `backend/scanner-core/EXTERNAL_SCANNERS.md` covers
the scanner binaries specifically.

## Documentation maintenance

This tree is maintained, not archived. See
[`CLAUDE.md`'s maintenance matrix](../CLAUDE.md#documentation-maintenance-matrix)
for what to update when you change something, and the
[source-of-truth rule](../CLAUDE.md#source-of-truth-rule) for what to do
when a document and the code disagree.
