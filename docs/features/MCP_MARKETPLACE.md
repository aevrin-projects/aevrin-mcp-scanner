# Aevrin Registry (formerly the MCP marketplace)

**Status: implemented** - an admin-curated registry of reusable
capabilities (MCP servers, skills, prompts, agents, templates, repositories
and 13 more types), browsed by people at `/marketplace` and queried by
agents over MCP. Registry ingestion from the official MCP Registry,
search, user suggestions, admin moderation, private org listings.
**Discovery only**: the registry does not scan, grade, or store any scan
state for any item (`DECISIONS.md` ADR-049). Payment processing for
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
**an administrator decides what is published**. It adds curation, ranking
and structured content (the prompt text, the skill's instructions, the
repository and ref to clone, a ready-to-copy client config) to what the
official [MCP Registry](https://registry.modelcontextprotocol.io) lists.

Publishing is curation, **not a security verdict**. The registry holds no
scan result, no grade and no scan state, for any item type, and says so on
the browse page. A user who wants to check an MCP server they found scans it
themselves with Aevrin's own scanner - see
[Scanning a server you found](#scanning-a-server-you-found).

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

Only `mcp_server` items carry an install recipe (`installation`), client
configs, a version list, and the "Scan with Aevrin" hand-off. No type
carries a security state.

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
  `review` and only an admin decision moves it on. An admin may publish
  many synced drafts at once with
  [Apply popularity bar](#publishing-qualifying-drafts), which is still
  an admin action and still goes through the publish gate per item.
- `archived` is reversible (restore returns it to `draft`). `delete`
  removes the row and everything that cascades from it, and requires the
  caller to type the item's slug.
- `status` is not in the edit allow-list. It changes only through
  `POST /admin/marketplace/mcp/{id}/status` (or deletion), so every change
  goes through the publish gate and leaves a `status_changed` event.

### The publish gate

`items.validate_item(row)` is the single definition of "may be
published", used by `admin.set_status` and by suggestion approval, and
returned as `validation_issues` by the admin item read. It returns the
reasons as sentences; the admin UI shows them verbatim and does not
pre-check anything itself. It is pure (reads only the row):

- a title and description;
- `content` and `installation` match their schemas. Packages of a type the
  official registry defines but no generated config can launch
  (`items.UNLAUNCHABLE_PACKAGE_TYPES`: `mcpb` bundles and `cargo` crates)
  are skipped, not refused, so Context7's bundle beside its npm package no
  longer blocks it; the config builder and the scan hand-off pick the first
  package they can launch. An empty `runtime_hint` (how the sync stores an
  absent one) means the registry type's default launcher; any other value
  outside the launcher allow-list is refused;
- per type: a `prompt` needs its prompt text, a `skill` its instructions,
  an `mcp_server` a package, a remote endpoint or a repository, a
  `repository` or `template` its repository URL; any other type needs a
  repository, a homepage, or usage or documentation text. Each type is
  checked by its own rule only: a remote-only or package-only MCP server
  with a description publishes (before 2026-09-29 it fell through to the
  generic rule and was refused for having "nothing to use").

`admin.set_status` runs the gate in a worker thread, because validating a
remote endpoint resolves its hostname (the SSRF guard), a blocking call.

### Publishing qualifying drafts

The registry holds tens of thousands of synced drafts; the sync keeps
landing new ones as drafts and does not change. `admin.bulk_publish`
(`GET` previews, `POST` publishes, `/admin/marketplace/bulk-publish`)
applies a fixed popularity bar (`DECISIONS.md` ADR-053, raised and made
two-way by ADR-054): it publishes the drafts that meet it and sets the
published MCP servers below it back to draft. The bar is constants in
`services/marketplace/admin.py`:

| Constant | Value | Meaning |
|---|---|---|
| `BULK_PUBLISH_FILTERS` | `status=draft`, `item_type=mcp_server`, `source=registry`, `visibility=public` | Synced public MCP server drafts only; an admin-made draft or an org's private item is never included |
| `BULK_PUBLISH_MIN_GITHUB_STARS` | `50` | The bar, in GitHub stars only; unknown stars do not meet it |
| `BULK_UNPUBLISH_FILTERS` | `status=published`, `item_type=mcp_server` | Published MCP servers the bar also applies to, whatever their source |
| `BULK_PUBLISH_MAX_PER_CALL` | `500` | Per call; the rest is `remaining` |
| `BULK_PUBLISH_CONCURRENCY` | `8` | Items in flight (gate checks and writes) |

A candidate stays a draft, counted once for the first reason that applies:
its repository already belongs to a published listing
(`already_published_repository`); it fails `validate_item` (`failed_gate`,
with the five most common reasons); another candidate for the same
repository is preferred (`duplicate_repository`: most `github_stars`, then
`npm_downloads_last_month`, then latest `updated_at`). Repositories are
compared by `admin.repository_key`: lowercased, trailing `/` and `.git`
removed. A draft with no repository is its own group. Qualifying drafts are
published most popular first.

The preview writes nothing. Publishing recomputes the set, then calls
`set_status` for each item, so each gets the publish gate again, its own
`status_changed` event and its own `registry.status.published` audit row;
one more audit row, `registry.bulk_publish`, records the criteria and the
counts. An item refused at that point (it changed since the read) is
returned in `failed` and stays a draft. Every published MCP server under
the bar (fewer than 50 stars, or stars not yet known) goes back to draft
through `set_status` in the same POST, with its own event and
`registry.status.draft` audit row; these are not capped per call, and a
listing leaving this way does not count as its repository being published,
so a better draft for the same repository can take its place. The metadata
refresh fills `github_stars` for more drafts over time, so a later run can
qualify drafts an earlier one did not.

There is no scan requirement. Before ADR-049 an MCP server could not be
published without a scan by the current engine (ADR-046); that gate went
with the registry's scanning.

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
that pass `network_safety.public_https_url_error`, because a remote is
copied into client configs and offered to the scan page as a target). Only
`mcp_server` items carry remotes and version rows.

### Versions

`mcp_listing_versions` is a bare list of versions the registry has seen:
`id`, `listing_id`, `version`, `first_seen_at` (migration `0049` dropped
every scan column). A row is added by the weekly sync for each new upstream
version, when a suggestion creates an MCP server (the tagged release, or
`unversioned`), when an admin creates an MCP server by hand
(`unversioned`), and when an admin edit changes `latest_version`. Editing
the install recipe or the repository does not add a version: versions are
what the publisher released, not a log of edits.

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
capability, price type and install target. There is no grade filter and no
security sort.
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
| `search_registry(query, type, category, technology, limit)` | Up to 25 compact items: slug, name, type, summary, categories, technologies, capabilities, use cases, web URL, and a note that listing is curation, not a security assessment |
| `get_registry_item(slug)` | Full metadata, `content`, install configs per client (with their warnings), repository and ref, related items |

Neither tool returns a security field, even if an older API sends one.
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
  **popularity 36%, maintenance 28%, community 18%, documentation 18%**
  (the previous 20/15/10/10 rescaled when the security component was
  removed). Popularity is log-scaled and takes the *max* signal. The score
  orders "Recommended"; it is never presented as a safety signal.
- **`catalog.py`** - search, detail (with `content`, `install_configs`,
  `versions` and `related`), categories, types, favourites, view counts,
  and `build_install_config`. `install_configs` carries one config per
  supported agent with its warnings (secret variables, an unpinned version,
  a remote operator's control); the install dialog, the "Use it" section
  and the registry MCP tools all read it, so there is one builder.
  Explicit column lists (`LIST_COLUMNS`, `DETAIL_COLUMNS`,
  `VERSION_COLUMNS`), never `select *`. Deliberately has **no "Verified"
  badge**: a verification claim needs documented criteria, and none exist.
- **`sync.py`** - the weekly job (`POST /scheduler/registry-sync`):
  incremental pull since the last successful sync, new servers inserted as
  `draft`, new versions recorded as bare version rows. For an item an admin has moved
  out of `draft`, sync updates only upstream-owned fields
  (`latest_version`, `registry_updated_at`, `registry_url`), so it never
  overwrites curation. `refresh_listing_metadata` refreshes GitHub and npm
  signals and licence, and is also what the admin "Refresh metadata"
  action calls.
- **`submissions.py`** - user suggestions. Validates the source URL
  (HTTPS only, GitHub classified before DNS resolution, otherwise the
  `network_safety.py` SSRF check), creates the item in `review` status, and
  approval runs the publish gate. The submission status `scanning` is
  legacy: nothing writes it, and the database check still allows it only
  because old rows may carry it.
- **`admin.py`** - create (from a URL or by hand, always `draft`,
  `source=admin`), edit, status changes, bulk publishing of qualifying
  drafts, delete, links, metadata refresh, categories. `EDITABLE_FIELDS` is a fixed allow-list with **no `status`
  and no `ranking_score`**. An edit that changes an MCP server's
  `latest_version` adds it to the version list.
  Every mutation writes `write_audit` (`registry.<action>`) and
  public-timeline changes also write `mcp_events`. Delete writes its audit
  row **before** deleting, with a snapshot of slug, title, type and
  repository, because `mcp_events` cascades away with the row.

## Scanning a server you found

The registry does not scan. An MCP server's detail page (and the admin item
editor's Install tab) shows **Scan with Aevrin**, built by
`entities/marketplace/model/scan-handoff.ts` from what the item declares:

| The item has | The hand-off |
|---|---|
| A `repository_url` on `github.com` with an owner and a repository | Link to `/scans/new?mode=github_repo&target=<url>` |
| Otherwise, an HTTPS remote endpoint (`installation.remotes[0].url`) | Link to `/scans/new?mode=live_mcp_server&target=<url>` |
| Otherwise, an `npm` or `pypi` package whose name and version are plain | The copyable CLI command `aevrin scan mcp "npx -y <pkg>[@version]"` (or `uvx` for PyPI) |
| None of these | Nothing |

Non-MCP items show no scan action at all. The link uses the scan page's
existing `mode` and `target` prefill (the same one `/agents/mcp` uses) and
mirrors its validation, so the form never refuses what the link put there.
The scan that runs is the canonical scanner (`POST /scans`), as the
signed-in user's own scan, against their own quota, recorded in their own
history. Nothing about it is written back to the registry.

`/marketplace` is public but `/scans` is protected. The auth proxy
(`frontend/src/shared/lib/supabase/proxy.ts`) sends a signed-out visitor to
`/login?next=<path and query>`, so the prefilled form survives sign-in.
Every consumer of `next` (the proxy, the login actions, `/auth/callback`)
goes through `shared/lib/safe-next.ts`, which accepts only a path starting
with a single `/` that still resolves to the app's own origin.

## Data

See [`../architecture/DATABASE.md`](../architecture/DATABASE.md).
Migration `0049` is a **contract** migration applied after the new API is
live: it drops `mcp_listings.current_*`, every scan column on
`mcp_listing_versions`, the `org_mcp_policies` table,
`tier_limits.marketplace_policies`, and cached `trust_grade` / `listing` AI
explanations. Historic `scans` rows with `invocation_channel =
marketplace` and `mcp_events` rows of type `scan_completed` /
`grade_changed` are kept; the item timeline hides those two event types.

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

- The registry makes no security claim about anything it lists. The
  browse page says so in a permanent banner.
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
publish gate with no scan requirement, remote-only and package-only MCP
servers publish while one with nothing installable or no description is
refused, suggestion approval through the same
gate, bare version rows from edits and the sync, sync lands drafts and does
not overwrite curation, delete audit order, links),
`test_marketplace_security.py` (ranking weights, no security sort, the
admin allow-list, and no security, grade or scan key in a decorated card, a
browse response model or a detail response, for every item type),
`tests/routes/test_registry_bulk_publish.py` (bulk publishing: the
criteria, one listing per repository within drafts and against published
listings, gate failures skipped, the preview writes nothing, a status,
event and audit row per item plus the summary row, the per-call cap, a
publish-time refusal reported, remote-only suggestion approval, and a
non-admin gets `404`),
`tests/routes/test_registry_routes.py` (admin guard on every route; the
scan, regrade, policy, scan-queue and install-plan routes and the grade
query parameters no longer exist), `test_marketplace_registry.py`,
`test_marketplace_hardening.py`;
`backend/cli/tests/test_registry_tools.py` (tool mapping, no security field
reaches an agent, untrusted README wrapping, the hosted server has no scan
tool, foreign `Host` refused). See
[`../testing/TESTING.md`](../testing/TESTING.md).

## Related docs

[`MCP_SCANNING.md`](MCP_SCANNING.md) (the scanner "Scan with Aevrin" hands
off to), [`../reference/CLI.md`](../reference/CLI.md)
(`aevrin mcp-server`), `frontend-docs/content/(marketplace)/*.mdx`
(user-facing).
