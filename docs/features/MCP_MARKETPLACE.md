# Aevrin Registry (formerly the MCP marketplace)

**Status: implemented** - an admin-curated registry of reusable
capabilities (MCP servers, skills, prompts, agents, templates, repositories
and 13 more types), browsed by people at `/marketplace` and queried by
agents over MCP. Registry ingestion from the official MCP Registry,
search, security grading of MCP servers, user suggestions, admin
moderation, private org listings, install policy. Payment processing for
third-party servers: **not built, and not planned** - the registry links to
a publisher's own pricing page and nothing more.

The file keeps its old name because other documents link to it. The code
also keeps its old names (`mcp_listings`, `/marketplace/mcp`,
`services/marketplace/`); see `DECISIONS.md` ADR-045 for why the table was
extended rather than renamed or duplicated.

User-facing product documentation for this feature lives in
`frontend-docs/content/(marketplace)/*.mdx` (published at
`docs.mcp.aevrin.net`) - read those for the exact promises made to end
users; this document covers the engineering structure behind them.

## Purpose

One place to find a capability an engineer or an agent can reuse, where
**an administrator decides what is published**. For MCP servers it adds
what the official [MCP Registry](https://registry.modelcontextprotocol.io)
deliberately leaves out: a real Aevrin security scan, curation, and
ranking. For every other type it adds curation and structured content (the
prompt text, the skill's instructions, the repository and ref to clone).

Aevrin is a downstream aggregator of the official MCP Registry - it reads
the registry's public API and stores what it reads as **drafts**. It does
not fork the registry or claim to replace it, and nothing it reads is
public until an admin publishes it.

## External sources and provenance

Three upstream services are read, never forked or mirrored as
authoritative: the official MCP Registry (`GET /v0.1/servers`, MIT
registry software, publisher-owned catalogue data), the GitHub REST API
(repository popularity and maintenance signals), and the npm registry API
(monthly download counts). All three are read-only HTTP; no code from any
of them is vendored.

Two other projects were read for architectural ideas, with no code taken:
[Glyph](https://github.com/HaseebKhalid1507/Glyph) (MIT) informed the
separation of static configuration analysis from runtime interception, and
[Cline's MCP Marketplace](https://github.com/cline/mcp-marketplace) (MIT)
informed the suggestion model: a submitter supplies a URL, metadata is
derived rather than typed, and a human reviews before publication.

One licensing distinction matters throughout this feature and is easy to
blur: the licences above are Aevrin's own supply chain. The licence shown
on a registry item (e.g. "MIT") is the *publisher's* licence for their
software, unrelated to any of this, and the registry never displays one in
place of the other.

## Item types

`items.ITEM_TYPES` is the one list, mirrored by the `item_type` check
constraint in migration `0048` and by `ItemType` in the frontend's
`entities/marketplace/model/types.ts`:

`mcp_server`, `skill`, `prompt`, `tool`, `agent`, `component`, `template`,
`workflow`, `library`, `cli`, `backend`, `frontend`, `infrastructure`,
`product`, `repository`, `integration`, `dataset`, `documentation`,
`other`.

**Only `mcp_server` has a security scanner** (`items.SCANNABLE_TYPES`).
Every other type is published without a grade and reported as
`not_applicable`, which the UI renders as "Not security-scanned by Aevrin.
Curated by an administrator." It is never shown as clean and never as
unscanned-and-suspicious: no scanner exists for a prompt, so either claim
would be invented.

## Lifecycle

```
          admin creates / sync ingests / suggestion approved
                               |
                             draft  <----------- restore ----------+
                               |                                   |
              publish (gate)   |   unpublish                       |
                               v                                   |
     suspended <---------- published ----------> archived ---------+
                               |
                          delete (typed slug confirmation, audited)
```

- `draft` is the only state any automated path creates. The weekly
  registry sync inserts new servers as `draft`; a suggestion is created in
  `review` and only an admin decision moves it on; a finished scan never
  changes status (before `0048` it set `published` unconditionally, which
  let a scan publish a draft or a suggestion with no admin decision).
- `archived` is reversible (restore returns it to `draft`). `delete`
  removes the row and everything that cascades from it, and requires the
  caller to type the item's slug.
- `status` is not in the edit allow-list. It changes only through
  `POST /admin/marketplace/mcp/{id}/status` (or deletion), so every change
  goes through the publish gate and leaves a `status_changed` event.

### The publish gate

`items.publish_blockers(db, row)` is the single definition of "may be
published", used by `admin.set_status` and by suggestion approval. It
returns the reasons as sentences; the admin UI shows them verbatim and
does not pre-check anything itself.

1. `validate_item(row)`: a title and description; `content` and
   `installation` match their schemas; per type - a `prompt` needs its
   prompt text, a `skill` its instructions, an `mcp_server` a package, a
   remote endpoint or a repository, a `repository` or `template` its
   repository URL; anything else needs a repository, a homepage, or usage
   or documentation text.
2. For an `mcp_server` only: the current version must have a scan **by the
   current engine** (`scans.scanner_name` is set, i.e. after the ToolTrust
   replacement) whose status is `completed` or `incomplete`. A `failed`
   run is a broken worker, not an assessment.

A grade is **not** required (`DECISIONS.md` ADR-046). A server that needs a
credential to start cannot be enumerated in a sandbox that holds none; its
honest result is "Scanned, not graded" (`scan_freshness` state
`ungraded`), shown as such, with the `REQUIRE_APPROVAL` policy and no
letter. What it may not be is unlooked-at.

## Content model

Migration `0048` adds these columns to `mcp_listings`:

- `item_type`, `author`, `repository_ref` (a branch, tag or commit;
  `admin._GIT_REF` restricts it to `[A-Za-z0-9._/-]`, no leading `-`, so it
  is safe to show inside a `git checkout` command);
- `technologies`, `capabilities`, `use_cases` (text arrays, normalised by
  the admin service, GIN-indexed for filtering);
- `content jsonb`, validated by `items.ItemContent` (extra keys forbidden,
  every field length-bounded): `prompt`, `instructions`, `usage`,
  `documentation`, `examples`, `inputs`, `outputs`, `dependencies`,
  `compatibility`.

`installation` (existing column) is validated by `items.InstallationSpec`:
packages (`npm`/`pypi`/`oci`/`nuget`, identifiers that look like a shell
command refused, runtime hint from a fixed set) and remotes (HTTPS URLs
that pass `network_safety.public_https_url_error`). Only `mcp_server`
items carry remotes and version rows.

Relations between items live in `mcp_listing_links (listing_id,
related_id, relation)` where `relation` is `uses` or `related`. The public
detail returns only targets that are `published` and public or unlisted,
so a link can never leak a draft or a private org item.

## Search and discovery

The index is the generated `search_vector` column: Postgres derives it from
the row (title weighted highest; then publisher, author and description;
then the item type, tags, categories, technologies, capabilities and use
cases; then the `content` instructions and usage text), so it cannot drift from the data
and "re-index" is not an operation. Queries go through
`websearch_to_tsquery`. There is no vector or semantic search
(`ROADMAP.md`).

`catalog.search_listings` filters by `item_type`, category, technology,
capability, minimum grade (MCP servers), price type and install target.
Sorts are in `ranking.SORT_ORDERS`; `trending` is views then favourites
among items updated in the last 30 days (`catalog.TRENDING_WINDOW`), and
the UI labels it "Most viewed this month", not "trending", because that is
what it measures. `GET /marketplace/types` returns per-type counts of
published public items for the type chips.

## Agent access (Aevrin MCP)

`backend/cli/aevrin_cli/registry_tools.py` is the single registry tool
module. It is an HTTP client of the public `/marketplace/*` endpoints -
read-only, unauthenticated, no local state - so an agent sees exactly
what an anonymous visitor sees: published, public items only. Three tools:

| Tool | Returns |
|---|---|
| `search_registry(query, type, category, technology, limit)` | Up to 25 compact items: slug, name, type, summary, categories, technologies, security state and grade, web URL |
| `get_registry_item(slug)` | Full metadata, `content`, install configs per client, repository and ref, related items, security summary |
| `list_registry_categories()` | Categories with item counts |

It is served two ways, from the same module:

- **Hosted:** `https://api.mcp.aevrin.net/mcp` (streamable HTTP, stateless,
  JSON responses), a separate `registry-mcp` container behind the same
  Caddy (`aevrin_cli/registry_mcp.py`, `Dockerfile.registry-mcp`). It
  registers **only** the three registry tools - never `scan_mcp_server`,
  which would let any caller start work on Aevrin's infrastructure. A test
  pins this. MCP protocol handling never runs inside FastAPI
  (`DECISIONS.md` ADR-047).
- **Local:** `aevrin mcp-server` (stdio) registers the registry tools next
  to `scan_mcp_server`.

A README is third-party text going straight into an agent's context, so
`get_registry_item` truncates it to 12,000 characters and prefixes it with
a notice that it is untrusted data, not instructions. Admin-authored
`content` is returned as written.

## Architecture

`backend/api/aevrin_api/services/marketplace/`:

- **`items.py`** - item types, the `content` and `installation` schemas,
  `validate_item`, and `publish_blockers`. The one place rules that differ
  by type live.
- **`normalize.py`** - registry `server.json` to a listing row.
  `registry_server_url()` is the single implementation of the "Listed via
  Official MCP Registry" link. The registry exposes no
  `GET /v0.1/servers/{name}` - only `/versions` and `/versions/{version}` -
  and the server name contains a literal `/` that must be percent-encoded.
  Categories and tags are inferred from the publisher's own vocabulary,
  never invented. Environment variables are reduced to
  name/required/secret; values are never captured.
- **`ranking.py`** - a fixed, documented formula, not a model:
  **security 45%, popularity 20%, maintenance 15%, community 10%,
  documentation 10%**. Popularity is log-scaled and takes the *max* signal,
  and an unscanned server scores `0` on security - never a neutral default
  that could be mistaken for "checked and fine."
- **`grading.py`** - delegates entirely to `scanner-core`'s `grade_scan()`.
  No second rubric exists here and no capability weights are added on top
  (the ADR-020/021 weights went when the engine became the grader;
  `DECISIONS.md` ADR-028 and ADR-033). Writes the grade onto a specific
  `mcp_listing_versions` row, and only this module writes
  `mcp_listings.current_*`. `scan_freshness` reports one of
  `not_applicable`, `unscanned`, `outdated`, `ungraded`, `partial`,
  `complete`.
- **`catalog.py`** - search, detail (with `content`, `install_configs`
  and `related`), categories, types, favourites, view counts, and
  `build_install_config` (shared by the detail page and the install-plan
  route). Explicit column lists, never `select *`. Deliberately has **no
  "Verified" badge**: a verification claim needs documented criteria, and
  none exist.
- **`sync.py`** - the weekly job (`POST /scheduler/registry-sync`):
  incremental pull since the last successful sync, new servers inserted as
  `draft`, new versions recorded unscanned. For an item an admin has moved
  out of `draft`, sync updates only upstream-owned fields
  (`latest_version`, `registry_updated_at`, `registry_url`), so it never
  overwrites curation. `refresh_listing_metadata` refreshes GitHub and npm
  signals and licence, and is also what the admin "Refresh metadata"
  action calls.
- **`scanning.py`** - reuses a prior scan when one already covers the
  exact version and wasn't `INCOMPLETE`; otherwise runs a real scan
  attributed to `MARKETPLACE_SCAN_USER_ID` (never a customer's account or
  quota), handed to `BackgroundTasks`. The target is the repository when
  there is one, otherwise the item's hosted remote endpoint (as a live
  MCP server scan); an item with neither raises `ScanNotPossible`. It never
  changes the listing's status.
- **`submissions.py`** - user suggestions. Validates the source URL
  (HTTPS only, GitHub classified before DNS resolution, otherwise the
  `network_safety.py` SSRF check), creates the item in `review` status, and
  approval runs the publish gate.
- **`admin.py`** - create (from a URL or by hand, always `draft`,
  `source=admin`), edit, status changes, delete, links, metadata refresh,
  categories, org policy. `EDITABLE_FIELDS` is a fixed allow-list with
  **no security-bearing column and no `status`**. Changing an MCP server's
  source (`repository_url`, `repository_ref`, `installation`,
  `latest_version`) opens a new version row, so the old grade stays with
  the version it was earned by and the item shows `outdated` until
  rescanned. Every mutation writes `write_audit` (`registry.<action>`) and
  public-timeline changes also write `mcp_events`. Delete writes its audit
  row **before** deleting, with a snapshot of slug, title, type and
  repository, because `mcp_events` cascades away with the row.

## Rescanning the catalogue

A server is scanned through `scan_listing_version`, which calls the same
`start_scan` the dashboard uses. There is no marketplace scanner, and the
scan records `invocation_channel = marketplace`.

The launch command comes from the version's own registry metadata when it
has any - `npm` becomes `npx -y <identifier>`, `pypi` becomes
`uvx <identifier>` - because the identifier a listing publishes is the
string a user would run. Identifiers carrying whitespace or shell
punctuation are refused outright.

`POST /admin/marketplace/mcp/regrade-ungraded` queues scans for MCP
servers (never other types, never rejected or archived items) that carry
no grade, in bounded batches. Items that cannot be scanned are reported as
skipped, with the reason. An unlaunchable server stays ungraded, which is
a result rather than an error.

## The letters

| Grade | Label | Suggested policy |
|---|---|---|
| A | Trusted | ALLOW |
| B | Generally safe | ALLOW |
| C | Caution | REQUIRE_APPROVAL |
| D | High risk | REQUIRE_APPROVAL |
| F | Do not use | BLOCK |

These are `GRADE_LABELS` and `GRADE_POLICIES` in
`aevrin_scanner_core/mcp/risk.py`, read by every surface. The policy is a
recommendation, never an automatic action. An org's install policy
(`org_mcp_policies.grade_actions`) defaults to the same actions; before
`0048` it had no entry for **F**, so an F server fell through to
`require_approval`. Migration `0048` adds `"F": "block"` to the default and
to every existing row, and `admin.evaluate_policy` falls back to the
per-grade default for any grade a stored policy omits.

There are no marketplace-specific overrides on top of the letter: the
engine assigns severities, the score and the letter per tool, rolled up to
the worst tool, and `grade_scan` chooses only the wording, the policy, and
whether the scan may carry a letter at all (`DECISIONS.md` ADR-033). An
unknown still counts against a grade, never for it: incomplete coverage,
no enumerable tools, or a failed run all mean **no letter**.

### Why a listing has the letter it has

The detail response carries `grade_rationale`: the severity counts and the
rules that earned the letter, ranked worst first, for the exact version the
letter belongs to. It is derived on read from that version's scan - the
same scan and ranking the scan report uses (`grade_drivers`) - so it cannot
disagree with the report. It is `null` when the graded version has no scan,
or that scan recorded no findings.

## Data

See [`../architecture/DATABASE.md`](../architecture/DATABASE.md). The
structural core of the feature: **security belongs to a version, never to
an item.** A grade is stored on `mcp_listing_versions`; when a publisher
ships v1.5.0, that version starts unscanned regardless of what v1.4.2
scored.

## Security

- Every admin route depends on `admin_identity`; a test walks the router
  table and fails if any `/admin/marketplace` route lacks it
  (`tests/routes/test_registry_routes.py`).
- Attack-scenario coverage for ingestion is in
  `tests/services/test_marketplace_hardening.py` - SSRF, scheme
  rejection, credential-pattern stripping, prompt-injection bounding.
- The hosted MCP endpoint only proxies public reads and pins its allowed
  `Host` header (`AEVRIN_MCP_ALLOWED_HOSTS`, others get `421`).

See [`../security/SECURITY.md`](../security/SECURITY.md#registry).

## Limitations (stated, not hidden)

- Rescans are triggered by evidence (new version, changed source, forced
  by an admin), never by a fixed timer; the UI states the scan's freshness
  rather than implying every grade is current.
- Popularity metrics are exactly what they measure: "GitHub stars," never
  "users".
- Private/org-scoped items are not searchable publicly and are never
  returned by the registry MCP tools.
- Not built for the pilot, deliberately (`ROADMAP.md`): collections,
  semantic search, registry prompts as native MCP `prompts`, rate limiting
  on the hosted MCP endpoint beyond Cloudflare's, and any "add to project"
  action that writes to a user's machine (Aevrin produces copyable config
  only).

## Testing

`backend/api/tests/services/test_registry.py` (types, validation, the
publish gate, sync lands drafts and does not overwrite curation, delete
audit order, links, policy F), `test_marketplace_scan_dispatch.py` (a scan
never changes status; hosted-endpoint targets),
`tests/routes/test_registry_routes.py` (admin guard on every route),
`test_marketplace_registry.py`, `test_marketplace_security.py`,
`test_marketplace_hardening.py`, `test_marketplace_grade_rationale.py`;
`backend/cli/tests/test_registry_tools.py` (tool mapping, untrusted README
wrapping, the hosted server has no scan tool, foreign `Host` refused). See
[`../testing/TESTING.md`](../testing/TESTING.md).

## Related docs

[`MCP_SCANNING.md`](MCP_SCANNING.md) (the grading function this feature
reuses), [`AI_REVIEW.md`](AI_REVIEW.md) (servers can carry an AI
explanation of their grade), [`../reference/CLI.md`](../reference/CLI.md)
(`aevrin mcp-server`), `frontend-docs/content/(marketplace)/*.mdx`
(user-facing).
