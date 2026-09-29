# API reference

Route inventory, extracted directly from `backend/api/aevrin_api/routes/`
(each domain's `APIRouter(prefix=...)` plus its decorated handlers) - not
restated from memory. This is a map to the code, not a second
specification that can drift from it: for exact request/response shapes,
read the route's own docstring (published as its OpenAPI `description`)
and its `schemas/` module, or the live `/docs` (FastAPI's generated Swagger
UI) against a running instance. Auth is `Authorization: Bearer` (Supabase
JWT) unless noted.

| Prefix | File | Routes |
|---|---|---|
| `/account` | `account.py` | `GET /usage` |
| `/admin` | `admin.py` | `GET /session`, `POST /totp/enrol`, `POST /totp/verify`, `GET /users`, `GET /users/{id}`, `POST /users/{id}/status`, `POST /users/{id}/plan`, `POST /users/{id}/seats`, `POST /users/{id}/overrides`, `DELETE /users/{id}/overrides/{bucket}`, `DELETE /users/{id}`, `POST /users/{id}/reset-usage`, `POST /users/{id}/password-reset`, `GET /analytics`, `GET /account-usage`, `GET /audit`, `GET /login-attempts` |
| `/admin/marketplace` | `admin_marketplace.py` | `GET /summary`, `GET /mcp`, `POST /mcp`, `GET /mcp/{listing_id}`, `PATCH /mcp/{listing_id}`, `POST /mcp/{listing_id}/status`, `DELETE /mcp/{listing_id}`, `PUT /mcp/{listing_id}/links`, `POST /mcp/{listing_id}/refresh-metadata`, `GET /submissions`, `POST /submissions/{id}/decision`, `GET /bulk-publish`, `POST /bulk-publish`, `GET /reports`, `POST /reports/{id}/decision`, `GET /categories`, `PUT /categories`, `DELETE /categories/{slug}` |
| `/agents` | `agents.py` | `POST /snapshots`, `GET ""`, `GET /mcp-servers`, `GET /skills`, `GET /permissions`, `GET /attack-paths`, `GET /{id}`, `DELETE /{id}` |
| `/ai` | `ai.py` | `GET /providers`, `PUT /providers`, `PATCH /providers/{provider}`, `DELETE /providers/{provider}`, `GET /models`, `POST /explain` |
| `/api-keys` | `api_keys.py` | `POST ""`, `GET ""`, `DELETE /revoked`, `DELETE /{key_id}` |
| `/auth` | `auth_lookup.py` | `GET /lookup` |
| `/billing` | `billing.py` | `GET /pricing`, `POST /checkout`, `POST /verify`, `POST /webhook`, `GET /subscription`, `GET /payments` |
| `/cli` | `cli.py` | `GET /precheck` (`X-API-Key`), `POST /upload` (`X-API-Key`) |
| `/device` | `device.py` | `POST /code`, `POST /token`, `GET /{user_code}`, `POST /{user_code}/approve` |
| `/events` | `events.py` | `POST /pageview` |
| `/scans` (export) | `export.py` | `GET /{scan_id}/export` |
| `/findings` | `findings.py` | `GET /{id}`, `PATCH /{id}` (`X-API-Key` accepted, for CLI triage) |
| `/github` | `github.py` | `GET /status`, `GET /repos`, `GET /install-url`, `GET /callback` |
| `/hook` | `hook.py` | `POST /override` (`X-API-Key`), `GET /cache`, `POST /cache` |
| `/marketplace` | `marketplace.py` | `GET /mcp`, `GET /types`, `GET /categories`, `GET /mcp/{slug}`, `POST /submissions`, `GET /submissions`, `POST /mcp/{id}/report`, `PUT /mcp/{id}/favorite`, `GET /favorites` |
| `/orgs` | `orgs.py` | `GET /permissions`, `GET /me`, `POST ""`, `PATCH ""`, `POST /leave`, `GET /members`, `PATCH /members/{id}`, `DELETE /members/{id}`, `GET /invites`, `POST /invites`, `DELETE /invites/{id}`, `POST /invites/{id}/accept`, `GET /roles`, `POST /roles`, `PATCH /roles/{id}`, `DELETE /roles/{id}` |
| `/scans` | `scans.py` | `POST ""`, `POST /upload` (`X-API-Key`), `GET /{id}/diff`, `GET ""`, `DELETE ""`, `GET /{id}`, `POST /{id}/cancel`, `DELETE /{id}`, `GET /{id}/stages`, `GET /{id}/findings` |
| `/scheduler` | `scheduler.py` | `POST /reap-stuck-scans`, `POST /registry-sync`, `POST /provider-sync`, `POST /uptime-check` - all gated by `require_scheduler_token` (HMAC comparison against `SCHEDULER_TOKEN`, fails closed if unconfigured), not a user session |
| `/status` | `status.py` | `GET /history` - **unauthenticated by design**: it is the data behind the public status page, which has to stay readable when nobody can sign in. Carries no user, org, or scan data. |

`GET /health` is registered directly in `main.py`, outside `ROUTERS`.

## Notable behavioral details worth knowing before calling a route

- **`GET /cli/precheck`** returns `402` with `{bucket, resets_at,
  upgrade_url}` when quota is exhausted, `401` for an invalid/revoked key -
  the CLI's `_authenticated_preflight()` renders both directly rather than
  making a scan attempt that would fail anyway.
- **`POST /cli/upload`** returns `422` with `OUTDATED_CLI_DETAIL` for a result
  from a pre-0.5.0 CLI, recognised by a finding `tool` or a stage name that the
  current engine does not produce. It is checked before any field is parsed,
  so an old client is told to upgrade rather than shown the first enum its
  payload trips. Old clients send no version header, so upload time is the
  earliest this can be detected for them; precheck cannot see it.
- **`PATCH /findings/{id}`** accepts either a user session or `X-API-Key`
  (the hook and `aevrin findings triage` both use the API key path).
  `false_positive` requires a `reason`.
- **Scan, finding and agent reads include the caller's workspace.** Every
  list and detail route under `/scans` (including `/stages`, `/findings`,
  `/diff` and `/export`), `GET /findings/{id}`, and every `GET /agents`
  route returns the caller's own rows plus rows stamped with their current
  workspace (ADR-052); another workspace's row, or a colleague's personal
  one, is `404`. `ScanOut` and the agent summaries carry `mine` and
  `created_by` (a colleague's email while they are a member, else `null`).
  `GET /scans` is still the 25 newest. `GET /scans/{id}/diff` compares
  against the previous scan by the scan's creator, and returns an empty diff
  when that scan is one the caller cannot read. `POST /scans/{id}/cancel`
  and `DELETE /scans` act on the caller's own scans only; `GET
  /account/usage` stays per person.
- **Workspace permissions return `403`.** For a caller in a workspace whose
  role lacks the permission, and a row that belongs to that workspace
  (whoever created it): `POST /scans`, `POST /scans/upload`, `POST
  /scans/{id}/cancel`, `GET /cli/precheck`, `POST /cli/upload` and `POST
  /agents/snapshots` need `scans.run`; `DELETE /scans/{id}` and `DELETE
  /scans` need `scans.delete` (the latter refuses the caller's whole history
  if any of their rows is a workspace row); `PATCH /findings/{id}` needs
  `findings.triage`; `DELETE /agents/{id}` needs `agents.delete`. The `detail` names the role, the
  permission's label and its key. A refused create spends no quota. `POST`
  and `GET /hook/cache` do not return `403` for this: with nothing cached
  they answer `decision: "not_permitted"` with the reason in `detail`, and
  start no scan. A caller in no workspace is never checked. See
  [`../security/SECURITY.md`](../security/SECURITY.md#authorization).
- **`GET /orgs/permissions`** is the whole catalogue (seven keys). `GET
  /orgs/roles` leaves out any stored key the catalogue no longer has, so the
  role editor never sends one back to `PATCH /orgs/roles/{id}`, which
  refuses unknown keys with `422`.
- **`/scheduler/*`** routes authenticate with a static bearer-style token,
  not a user or API-key identity - they're meant to be called by an
  external scheduler (EventBridge, a cron container), not a human.
- **`GET /marketplace/mcp/{slug}`** returns `404`, not `403`, for a private
  listing the caller isn't authorized to see - existence itself isn't
  leaked to an unauthorized caller. It carries `install_configs` (one
  client config per supported agent, each with its `warnings`), which is
  what the install dialog shows; there is no separate install-plan route.
- **`/marketplace/mcp` serves every registry item type, not only MCP
  servers.** The path predates the registry and is kept because clients
  (the frontend, the registry MCP tools, the CLI) already call it; the
  `mcp` segment is naming debt, not a filter. Filter by type with
  `?type=` (also `technology`, `capability`, `category`, `price_type`,
  `install_target`, `sort=trending`). Anonymous callers see only published
  public items. **The registry is discovery only**: no registry response
  carries a scan result, a grade or a scan state, and there is no grade
  filter or security sort (`DECISIONS.md` ADR-049). Scanning is `POST
  /scans`.
- **`admin_marketplace.py`**'s edit route (`PATCH /mcp/{listing_id}`)
  writes only from `services/marketplace/admin.py`'s `EDITABLE_FIELDS`
  allow-list, which contains no `status` - publishing goes only through
  `POST /mcp/{listing_id}/status`, which runs the publish gate
  (`items.validate_item`, no scan requirement) and returns `400` with the
  reasons when it refuses.
- **`DELETE /admin/marketplace/mcp/{listing_id}`** takes a body
  `{"confirm_slug": "<the item's slug>"}` and refuses without an exact
  match. **`DELETE /admin/marketplace/categories/{slug}`** is refused while
  any item is filed under the category.
- **`GET /admin/marketplace/bulk-publish`** previews and **`POST
  /admin/marketplace/bulk-publish`** runs "Apply popularity bar"
  (`admin.bulk_publish`, criteria in `docs/features/MCP_MARKETPLACE.md`,
  `DECISIONS.md` ADR-053). No body. Both return `BulkPublishResult`:
  `{dry_run, criteria, considered, qualifying, batch, published, failed:
  [{id, slug, reason}], remaining, skipped: {already_published_repository,
  failed_gate, duplicate_repository}, gate_reasons: [{reason, count}],
  sample: [{id, slug, title, repository_url, github_stars,
  npm_downloads_last_month}], below_bar, unpublished, below_bar_sample}`
  (samples at most 20, gate reasons the top 5). The preview writes nothing.
  The POST recomputes the set, publishes at most 500 per call and sets every
  published MCP server under the bar back to draft, each through
  `set_status` (an event and an audit row per item), and writes one
  `registry.bulk_publish` audit row; `remaining` > 0 means call again.

- **`POST /billing/checkout`** takes `{tier, cycle, seats}`. For Team,
  `seats` is 3-500 and the amount is the per-seat price times `seats`; it
  returns `409` when the caller is in a workspace they do not own, or when
  `seats` is below the workspace's members plus live invites. **`POST
  /billing/verify`** returns `409` when nothing was granted, rather than
  "ok". **`POST /billing/webhook`** checks the signature before parsing the
  body and settles on `payment.captured` or `order.paid`.
- **`GET /billing/subscription`** returns `effective_tier` as the tier
  enforced (including Team inherited from a workspace), plus
  `own_effective_tier`, `seats` and `seats_used` (owners only).
  **`GET /account/usage`** reports the enforced tier too.
- **`POST /admin/users/{id}/seats`** takes `{seats 1-500, reason,
  totp_code}` and returns `404` when the account has no row.
  **`GET /admin/users/{id}`** adds `entitled_tier`, `workspace` and
  `payments`; **`GET /admin/analytics`** adds `revenue_by_currency`, in
  minor units per currency, never summed across currencies.

## Error responses and the CDN

An upstream PostgREST failure returns **500**, not 502. 502 is the more
accurate word - this API is a gateway in front of PostgREST - but Cloudflare
replaces an origin 502 with its own plain-text error page, which carries none
of the CORS headers `CatchUnhandledErrorsMiddleware`'s ordering exists to
guarantee. The browser then sees no response rather than a refused one, and
the dashboard reports a connectivity error for what was a query fault. Any
new error status this API returns has to survive the same trip: if Cloudflare
would substitute its own page for it, the client learns nothing.

## Adding a route

New file in `routes/`, registered in `routes/__init__.py`'s `ROUTERS` list
- that's the only place a router needs adding; `main.py` never changes for
a new domain. Update this file and
[`../architecture/BACKEND.md`](../architecture/BACKEND.md) in the same
change, per `CLAUDE.md`'s
[maintenance matrix](../../CLAUDE.md#documentation-maintenance-matrix).
