# MCP marketplace

**Status: implemented** - registry ingestion, search, security grading,
submissions, admin moderation, private org listings, install policy.
Payment processing for third-party servers: **not built, and not
planned** - the marketplace links to a publisher's own pricing page and
nothing more.

User-facing product documentation for this feature lives in
`frontend/content/(marketplace)/*.mdx` (published at
`docs.mcp.aevrin.net`) - read those for the exact promises made to end
users; this document covers the engineering structure behind them.

## Purpose

A catalogue of MCP servers with a real Aevrin security scan attached to
each one, so "should I install this" has an answer before installing,
rather than after. Aevrin is a downstream aggregator of the official
[MCP Registry](https://registry.modelcontextprotocol.io) - it reads the
registry's public API, stores what it reads, and adds three things the
registry deliberately leaves out: a security scan, curation, and ranking.
It does not fork the registry or claim to replace it.

## External sources and provenance

Three upstream services are read, never forked or mirrored as
authoritative: the official MCP Registry (`GET /v0.1/servers`, MIT
registry software, publisher-owned catalogue data), the GitHub REST API
(repository popularity and maintenance signals), and the npm registry API
(monthly download counts). All three are read-only HTTP; no code from any
of them is vendored.

Two other projects were read for architectural ideas, with no code taken:
[Glyph](https://github.com/HaseebKhalid1507/Glyph) (MIT) informed the
separation of static configuration analysis from runtime interception -
Aevrin's own detection and tool-discovery code in
`scanner-core/analysis/mcp_detection.py` was written from the MCP
specification and the SDKs' own registration APIs, not copied from it.
[Cline's MCP Marketplace](https://github.com/cline/mcp-marketplace) (MIT)
informed the submission model: a submitter supplies a URL, metadata is
derived rather than typed, and a human reviews before publication - the
shape `services/marketplace/submissions.py`'s state machine follows.

One licensing distinction matters throughout this feature and is easy to
blur: the licences above are Aevrin's own supply chain. The licence shown
on a marketplace listing (e.g. "MIT") is the *MCP publisher's* licence for
their software, unrelated to any of this, and the marketplace never
displays one in place of the other.

## User workflow

Browse/search (`/marketplace`), view a listing's grade and sub-scores
(`/marketplace/[slug]`), save one (`/marketplace/saved`), submit a new one
for review (`/marketplace/submit`), install via a generated config
snippet with blank secrets (never a real value). Admins moderate via
`/admin/marketplace`.

## Architecture

`backend/api/aevrin_api/services/marketplace/`:

- **`normalize.py`** - registry `server.json` → a listing row.
  `registry_server_url()` is the single implementation of the "Listed via
  Official MCP Registry" link, used at ingestion and again at read time.
  The registry exposes no `GET /v0.1/servers/{name}` - only
  `/versions` and `/versions/{version}` - and the server name contains a
  literal `/` that must be percent-encoded or the registry's router reads
  it as a path separator. Getting either wrong produces the same 404, and
  both were wrong initially. Categories
  and tags are inferred from the publisher's own vocabulary (a keyword
  table, 17 seeded categories, `["other"]` fallback) - never invented.
  Install targets are derived only from declared transports; environment
  variables are reduced to name/required/secret, values are never
  captured.
- **`ranking.py`** - a fixed, documented formula, not a model:
  **security 45%, popularity 20%, maintenance 15%, community 10%,
  documentation 10%**. Popularity is log-scaled and takes the *max* signal
  (stars/downloads), not a sum, and an unscanned listing scores `0` on the
  security component - never a neutral default that could be mistaken for
  "checked and fine."
- **`grading.py`** - delegates entirely to `scanner-core`'s
  `grade_mcp_server()`. No second rubric exists here. Writes the grade
  onto a specific `mcp_listing_versions` row, and only that function
  writes `mcp_listings.current_*` (the maintained projection - see
  [`../architecture/DATABASE.md`](../architecture/DATABASE.md)).
- **`catalog.py`** - search, listing detail, category listing, favorites,
  view counts. Explicit column lists (`LIST_COLUMNS`/`DETAIL_COLUMNS`),
  never `select *`. Deliberately has **no "Verified" badge** - a
  verification claim needs documented criteria, and none exist, so the
  badge doesn't either. `decorate()` recomputes `registry_url` from
  `normalize.registry_server_url()` rather than returning the stored
  column: the URL is derived data, and rows written before the format was
  corrected would otherwise keep serving a link that 404s until a re-sync
  that nothing currently schedules.
- **`sync.py`** - the weekly job (`POST /scheduler/registry-sync`):
  incremental pull since the last successful sync (a watermark, minus a
  one-hour overlap margin), new versions recorded unscanned, metadata
  refresh on a budget with bounded concurrency, ranking recompute.
- **`scanning.py`** - reuses a prior scan when one already covers the
  exact version and wasn't `INCOMPLETE`; otherwise runs a real scan
  attributed to `MARKETPLACE_SCAN_USER_ID` (never a customer's account or
  quota).
- **`submissions.py`** - validates the source URL (HTTPS only, GitHub
  classified before DNS resolution, otherwise the same
  `network_safety.py` SSRF check used by live-server scanning), creates
  the listing in `review` status - **never `published`** - and refuses
  approval without a completed scan.
- **`admin.py`** - a fixed `EDITABLE_FIELDS` allow-list containing **no
  security-bearing column**; every override writes an audit event
  (before/after/reason/actor/timestamp). Publish refuses an unscanned
  listing.

## The letters

| Grade | Label | Recommended action |
|---|---|---|
| A | Trusted | Allow |
| B | Generally safe | Allow with caution |
| C | Caution | Require approval |
| D | High risk | Block |

Two overrides always win over the weighted arithmetic: **any open critical
finding is a D**, and **unauthenticated command execution is a D** - both
regardless of how good everything else looks. An unknown (coverage gap,
unresolvable auth state) always counts against a grade, never for it.

## Data

See [`../architecture/DATABASE.md`](../architecture/DATABASE.md) for the
full table list. The one fact worth repeating here because it's the
structural core of the whole feature: **security belongs to a version,
never to a listing.** A grade is stored on `mcp_listing_versions`; when a
publisher ships v1.5.0, that version starts unscanned regardless of what
v1.4.2 scored. A catalogue that carried last month's grade onto this
week's release would be publishing a claim with no evidence behind it.

## Security

Full attack-scenario coverage in
`backend/api/tests/services/test_marketplace_hardening.py` - SSRF,
scheme rejection, credential-pattern stripping, prompt-injection bounding.
See [`../security/SECURITY.md`](../security/SECURITY.md).

## Limitations (stated, not hidden)

- Rescans are triggered by evidence (new version, changed source hash,
  forced by an admin), never by a fixed timer - a listing can carry a
  grade that's technically stale between evidence events; the UI states
  the scan's freshness (`complete`/`partial`/`outdated`/`unscanned`)
  rather than implying every grade is current.
- Popularity metrics are exactly what they measure and nothing more - a
  download count includes every CI run that ever installed the package;
  the UI labels them precisely ("GitHub stars," never "users") rather than
  implying a more meaningful number.
- Private/org-scoped listings are not searchable publicly and don't appear
  in public rankings - visible only to authorized org members (RLS
  `check` constraint pairs `visibility='private'` with a non-null `org_id`
  or neither, never one without the other).

## Testing

`backend/api/tests/services/test_marketplace_registry.py`,
`test_marketplace_security.py`, `test_marketplace_hardening.py`. See
[`../testing/TESTING.md`](../testing/TESTING.md).

## Related docs

[`MCP_SCANNING.md`](MCP_SCANNING.md) (the grading function this feature
reuses), [`AI_REVIEW.md`](AI_REVIEW.md) (marketplace listings can carry an
AI explanation of their grade), `frontend/content/(marketplace)/*.mdx`
(user-facing).
