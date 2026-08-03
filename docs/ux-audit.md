# Aevrin Authenticated UX Audit

Date: August 3, 2026
Mode: `aevrin-product-ux-overhaul full`
Source of truth: current repository, local app at `http://localhost:3000`, local API at `http://127.0.0.1:8000`, Supabase project `onwijviiwtuwldjmqoam`

## Visual References

- Available:
  - `Aevrin_MCP_Scanner_Specification.docx`
  - Local before screenshots captured from the running app:
    - `docs/screenshots/before/1440-dashboard.png`
    - `docs/screenshots/before/1440-scan.png`
    - `docs/screenshots/before/1440-api-keys.png`
    - `docs/screenshots/before/1440-billing.png`
    - equivalent `1024`, `768`, and `390` variants
- Unavailable:
  - `Screenshot 2026-08-03 at 1.14.48 PM.png`
  - `Screenshot 2026-08-03 at 1.14.59 PM.png`
  - `Screenshot 2026-08-03 at 1.15.07 PM.png`

## Route Inventory

### `/dashboard`

- Purpose before redesign: new scan form plus recent scans.
- Data sources:
  - `GET /scans`
  - `POST /scans`
  - `GET /account/usage`
- Confirmed problems:
  - `high`: content constrained to a narrow centered column on a large viewport, leaving most of the authenticated product empty.
    - Evidence: `docs/screenshots/before/1440-dashboard.png`
    - Affected files: `apps/web/src/app/dashboard/page.tsx`, `apps/web/src/components/nav-bar.tsx`
  - `high`: primary product metric is usage quota rather than security posture or urgent work.
    - Evidence: source and live page structure
    - Affected files: `apps/web/src/app/dashboard/page.tsx`, `apps/web/src/components/usage-meters.tsx`
  - `high`: no persistent app shell, weak active navigation, and account identity displayed as a top-level nav item.
    - Evidence: `docs/screenshots/before/1440-dashboard.png`, `docs/screenshots/before/390-dashboard.png`
    - Affected files: `apps/web/src/components/nav-bar.tsx`
  - `medium`: no first-run onboarding; empty state is essentially blank recent-scan skeletons or “No scans yet.”
    - Evidence: `docs/screenshots/before/390-dashboard.png`
    - Affected files: `apps/web/src/app/dashboard/page.tsx`
  - `medium`: GitHub, live server, and config modes are present but operational context is weak and quota is separated from the decision point.
    - Evidence: live page and source
    - Affected files: `apps/web/src/app/dashboard/page.tsx`

### `/scans/[id]`

- Purpose before redesign: shared progress and result screen.
- Data sources:
  - `GET /scans/{id}`
  - `GET /scans/{id}/stages`
  - `GET /scans/{id}/findings`
  - `GET /scans/{id}/export`
- Real audited scan:
  - target: `https://github.com/modelcontextprotocol/servers`
  - status: `incomplete`
  - score: `100`
  - unreliable stages: `static_analysis`, `secrets`
  - limitation finding only: MCP08 not tested
- Confirmed problems:
  - `blocker`: partial scan can still display `100` with “Clean” language and zero active findings, even when key stages failed.
    - Evidence: `docs/screenshots/before/1440-scan.png`
    - Affected files: `apps/web/src/app/scans/[id]/scan-detail-client.tsx`, `apps/web/src/lib/scoring.ts`
  - `high`: stage failures are present but not organized as a coverage model the user can act on.
    - Evidence: live result state and API payload
    - Affected files: `apps/web/src/app/scans/[id]/scan-detail-client.tsx`
  - `high`: no search or filters for findings, no preserved result context, and no route back to a filtered list.
    - Evidence: source
    - Affected files: `apps/web/src/app/scans/[id]/scan-detail-client.tsx`, `apps/web/src/app/scans/[id]/findings/[findingId]/finding-detail-client.tsx`
  - `medium`: target, time, duration, score method, and scanner coverage are incomplete or visually weak.
    - Evidence: `docs/screenshots/before/1440-scan.png`
    - Affected files: `apps/web/src/app/scans/[id]/scan-detail-client.tsx`

### `/scans/[id]/findings/[findingId]`

- Purpose before redesign: finding detail and triage.
- Data sources:
  - `GET /findings/{findingId}`
  - `PATCH /findings/{findingId}`
- Confirmed problems:
  - `high`: back navigation loses any result context because the route only links back to `/scans/{id}`.
    - Evidence: source
    - Affected files: `apps/web/src/app/scans/[id]/findings/[findingId]/finding-detail-client.tsx`
  - `high`: false-positive suppression is exposed without a required reason or auditable trail in the current UI.
    - Evidence: source and backend schema
    - Affected files: `apps/web/src/app/scans/[id]/findings/[findingId]/finding-detail-client.tsx`, `apps/api/src/aevrin_api/routers/findings.py`
  - `medium`: metadata is sparse and the layout does not clearly separate context, explanation, remediation, and scanner provenance.
    - Evidence: source
    - Affected files: `apps/web/src/app/scans/[id]/findings/[findingId]/finding-detail-client.tsx`

### `/settings/api-keys`

- Purpose before redesign: create and revoke dashboard API keys.
- Data sources:
  - `GET /api-keys`
  - `POST /api-keys`
  - `DELETE /api-keys/{id}`
- Confirmed problems:
  - `high`: creation flow reveals the secret once, but there is no copy affordance, revoke confirmation, or operational guidance.
    - Evidence: `docs/screenshots/before/1440-api-keys.png`
    - Affected files: `apps/web/src/app/settings/api-keys/page.tsx`
  - `medium`: key list is too bare for a security product and collapses into a single empty line when no keys exist.
    - Evidence: `docs/screenshots/before/1440-api-keys.png`
    - Affected files: `apps/web/src/app/settings/api-keys/page.tsx`
  - `medium`: prefix, scopes, and expiry are absent from backend responses, so the UI must not fabricate them.
    - Evidence: `apps/api/src/aevrin_api/schemas.py`

### `/settings/billing`

- Purpose before redesign: plan status.
- Data sources:
  - `GET /billing/subscription`
  - `GET /account/usage`
- Confirmed problems:
  - `high`: page is mostly empty and does not explain plan behavior, usage, reset timing, or what “no auto-renewal” means in practice.
    - Evidence: `docs/screenshots/before/1440-billing.png`
    - Affected files: `apps/web/src/app/settings/billing/page.tsx`
  - `medium`: upgrade CTA exists, but there is little operational context around limits or paid-until behavior.
    - Evidence: live page and API payload
    - Affected files: `apps/web/src/app/settings/billing/page.tsx`

## Information Architecture Problems

- `high`: authenticated navigation exposed only three destinations and mixed product navigation with theme and sign-out controls.
- `high`: there was no overview page, no scan history page, and no integrations landing page despite those being primary product tasks.
- `medium`: the new-scan form and recent scan list shared one narrow page with no task hierarchy.

## Accessibility and Responsive Problems

- `high`: desktop layout wasted most of a `1440px` viewport.
- `high`: mobile layout reduced the already-thin information architecture to three tiny top-nav items plus sign-out.
- `medium`: typography and metadata were legible but too faint and too low in hierarchy for a security product.
- `medium`: task screens lacked a skip link and coherent landmarks inside the authenticated experience.

## Security and Product-Truth Constraints Verified

- Confirmed backend-only truths:
  - API keys expose `name`, `created_at`, `last_used_at`, and `revoked_at`; they do not expose masked prefix, expiry, or scopes.
  - Billing exposes `tier`, `effective_tier`, `paid_until`, and bucket usage; it does not expose invoices or current billing cycle selection.
  - Findings triage supports `open`, `fixed`, and `false_positive`; no reason field is currently stored.
  - Global cross-scan findings endpoint does not exist, so a fake global findings queue would violate product truth.
- Confirmed current product risk:
  - incomplete scans can produce a perfect score if failed scanners produced no completed findings, so the UI must foreground scan completeness and failed stages.

## Proposed Fixes Implemented in This Overhaul

- Replace the thin top nav with a real authenticated shell: sidebar, mobile drawer, active nav, account menu, and consistent page headers.
- Split the product flow into `Overview`, `New scan`, `Scan history`, `Integrations`, `API keys`, `Billing`, `Scan result`, and `Finding detail`.
- Move quota to a secondary module and prioritize critical findings, high findings, scans requiring attention, latest scan status, and target coverage.
- Expose honest partial-scan language, stage failures, limitation notices, and score explanation together.
- Add search and filtering on scan findings plus encoded return navigation to preserve context when opening a finding.
- Harden API-key UX with copy affordances, safer one-time reveal, revoke confirmation, and no simulated unsupported fields.
- Expand billing into plan behavior plus real usage buckets without fabricating invoices or renewal data.

## Remaining Backend-Driven Limitations

- No masked API-key prefix exists in the backend response yet.
- False-positive suppression cannot require a reason until the backend stores one.
- No cross-scan findings endpoint exists for a trustworthy global findings queue.
- Billing still lacks invoices, current cycle selection, and payment history in authenticated APIs.
