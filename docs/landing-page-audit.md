# Aevrin Product and Landing-Page Audit

Date: August 3, 2026  
Production: `https://mcp.aevrin.net`  
Scope: public site, authenticated workspace, API, scanner pipeline, Supabase persistence, and Railway runtime

## Evidence baseline

- Production screenshots: `apps/web/docs/screenshots/audit-prod/`
- Authenticated before/after screenshots: `docs/screenshots/before/` and `docs/screenshots/after/`
- 21st.dev references inspected with Playwright:
  - `docs/screenshots/21st-components-baseline.png`
  - `docs/screenshots/21st-dashboard-components.png`
  - `docs/screenshots/21st-advanced-stats.png`
- Live database records: recent `scans`, `scan_stages`, `findings`, and `tier_limits` queried on August 3, 2026.
- Railway evidence: API deployment healthy, 0% sampled HTTP error rate, peak memory approximately 2.66 GB during overlapping scans.

## Confirmed defects

| Route or system | Severity | Category | Current behavior and evidence | Correction | Source files |
|---|---:|---|---|---|---|
| Scanner worker | Blocker | Engineering / trust | Two scans of the same repository overlapped. The first completed in about 65 seconds; the second ended in about 4 seconds with Semgrep, Bandit, Gitleaks, TruffleHog, Trivy, and Scorecard failures. Railway memory peaked near 2.66 GB. | Bound concurrent scan execution, preserve queued/running state, and persist terminal failures instead of leaving scans stuck. | `apps/api/src/aevrin_api/scan_service.py`, `apps/api/src/aevrin_api/config.py` |
| Tool-description stage | High | Factual / trust | A repository with detected MCP SDK usage is shown as `failed` when no safe runnable MCP client entrypoint is present: “no MCP server entrypoint discovered.” | Mark this as `skipped` coverage with a plain explanation; do not represent an inapplicable runtime check as a broken scanner. | `packages/scanner-core/src/aevrin_scanner_core/pipeline.py` |
| Scan lifecycle | High | Engineering | The scan row remains `queued` while the pipeline is already running, and an uncaught pipeline exception can leave a scan permanently queued/running. | Persist `running` when a worker acquires capacity and persist a safe `failed` state and completion timestamp on exceptions. | `apps/api/src/aevrin_api/scan_service.py` |
| Finding detail | High | Trust / auditability | `triage_status=false_positive` exists and is used in production, but the UI suppresses the action because no reason or triage timestamp is stored. | Add reason and timestamp fields, require a reason for false-positive reports, expose reopen/fixed/false-positive actions, and retain the audit data. | `infra/migrations/`, `apps/api/src/aevrin_api/schemas.py`, `apps/api/src/aevrin_api/routers/findings.py`, `apps/web/src/app/scans/[id]/findings/[findingId]/finding-detail-client.tsx` |
| Scan history | High | Usability / privacy | There is no clear-history control and no individual deletion action despite privacy copy describing deletion. History loading also performs two additional API requests per scan. | Add owner-scoped single and bulk deletion, confirmations, optimistic refresh, empty/error states, and a summary endpoint to avoid N+1 requests. | `apps/api/src/aevrin_api/routers/scans.py`, `apps/web/src/app/scans/history/page.tsx`, `apps/web/src/lib/api.ts` |
| Usage | High | Usability | Usage is embedded as a small secondary module and billing detail. There is no dedicated usage route or attributed activity ledger. | Add `/usage`, a navigation item, KPI-style bucket cards, exact reset context, source filters, and the latest 50 dashboard/CLI/hook scans with report links. | `apps/api/src/aevrin_api/routers/account.py`, `apps/web/src/app/usage/page.tsx`, `apps/web/src/components/authenticated-app-shell.tsx` |
| Integrations | High | Responsive | The desktop screenshot at the supplied viewport shows three fixed-width install cards overflowing their panel, clipped copy buttons, and nested horizontal scrolling. | Replace fixed columns with fluid responsive grids, wrap command actions, and allow code blocks—not whole cards—to scroll. | `apps/web/src/app/integrations/page.tsx`, `apps/web/src/components/install-docs-section.tsx` |
| Authenticated shell | Medium | Responsive | The sidebar consumes 296–320 px and page content has large horizontal padding; at common laptop widths this compresses complex cards and tables. | Use a narrower fluid sidebar, cap only readable text—not the workspace—and remove width assumptions from child grids. | `apps/web/src/components/authenticated-app-shell.tsx`, authenticated pages |
| Unknown public route | Medium | Routing / usability | `/definitely-not-a-real-route` responds with HTTP 200 and redirects to `/login`, so public typos do not receive a real 404. | Add a public not-found boundary and exclude genuinely unknown routes from auth redirection. | `apps/web/src/proxy.ts`, `apps/web/src/app/not-found.tsx` |
| Public pages | Low | SEO | Landing has an H1, but `/pricing`, `/docs`, and `/login` expose no semantic H1 in the rendered DOM. All routes share the same generic page title. | Add route metadata and one semantic H1 per public page without changing verified product claims. | public route pages and layout |

## Confirmed working or already corrected

- Partial scans are labeled `incomplete`, unreliable stages are persisted, and the score is explicitly described as reflecting completed checks only.
- The score formula remains severity weighted and is not altered for marketing.
- Public landing, pricing, docs, login, status, terms, and privacy pages load at 1440, 1024, and 390 px without console errors.
- False-positive state is already a valid stored triage status; the missing work is the auditable report reason and complete UI.
- API ownership checks scope scan/finding reads and updates to the authenticated user.
- Terms and privacy pages are no longer visibly labeled draft in the captured production pages.

## Assumptions and external checks

- Supabase migrations `0010`–`0012` were applied through the authorized production SQL editor. Live PostgREST checks confirm the source and triage columns, and no unredacted pasted-configuration targets remain.
- No production authentication credential was available to Playwright. Authenticated visual checks use the repository's existing real-data screenshots plus local component/API verification until a safe test account is available.
- A canceled Next.js RSC prefetch appears as `net::ERR_ABORTED` in Playwright during navigation. These are not treated as route failures because the requested document responses completed with HTTP 200 and no console errors.
