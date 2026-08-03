# Aevrin Authenticated UX Architecture

Date: August 3, 2026

## Navigation

- Overview
- New scan
- Scan history
- Integrations
- API keys
- Billing

Hidden until real backend support exists:

- Global findings
- Reports index
- Workspace settings beyond billing and API keys

## Core User Flow

`Overview -> New scan -> Scan result -> Finding detail -> Rescan`

Supporting flows:

- `Overview -> Scan history -> Scan result`
- `Overview -> Integrations -> CLI or hook setup`
- `Overview -> API keys -> Create or revoke automation key`
- `Overview -> Billing -> Review plan behavior and usage`

## Screen Responsibilities

### Overview

- Show the current attention queue using only real data from recent scans and findings.
- Prioritize:
  - active critical findings
  - active high findings
  - scans requiring attention
  - latest scan status
  - scanned targets
- Keep usage secondary.
- For first-run users, replace analytics with onboarding and one dominant CTA.

### New scan

- Focus on one task: start a scan.
- Keep the three input modes explicit.
- Pair each mode with its real coverage and limitation statement.
- Keep quota at the decision point, not as the hero statistic.
- Show recent scans in a secondary column.

### Scan history

- Expose search and filters across the existing scan list.
- Show target, target type, finish time, duration, status, and critical/high counts.
- Link each row directly into the result screen.

### Scan result

- Answer:
  - What was scanned?
  - How complete was the scan?
  - What needs attention first?
  - What was not tested?
- Keep score adjacent to completion state and stage coverage.
- Separate active findings from limitation notices.
- Preserve filter state when opening a finding.

### Finding detail

- Show severity, status, scanner source, OWASP category, location, explanation, and remediation.
- Preserve the link back to the prior filtered result view.
- Expose only triage actions that remain defensible against the current backend contract.

### Integrations

- Keep CLI and Claude Code hook onboarding concise.
- Make copy actions explicit.
- Prefer interactive login over long-lived secrets for developer use.

### API keys

- Treat keys as automation credentials, not the primary sign-in path.
- Reveal the full secret once only.
- Confirm revocation.
- Avoid unsupported prefix, scope, or expiry claims.

### Billing

- Explain what the current plan is and how one-cycle payments work.
- Show usage buckets and reset dates from real account data.
- Avoid fake invoices, impossible renewal logic, or unsupported payment actions.

## Responsive Model

- Desktop: persistent sidebar and full-width content up to roughly `1320px`.
- Tablet: same shell with collapsed content density.
- Mobile: drawer navigation, stacked headers, and card-based result sections.

## Content Model

- Operational copy only.
- Security score never stands alone.
- Every empty state explains what to do next.
- Every error state explains what failed and whether partial data remains usable.
